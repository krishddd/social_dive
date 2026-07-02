"""
YouTube channel — extract video transcripts and metadata.

Backends (ordered fallback):
  1. youtube-transcript-api — direct transcript extraction (no download)
  2. yt-dlp — subtitle file download (needs yt-dlp installed)
"""

from __future__ import annotations

import re

from loguru import logger

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchNotSupportedError,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel
from social_dive.probe import probe_command, probe_python_import


@register_channel
class YouTubeChannel(Channel):
    name = "youtube"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["youtube-transcript-api", "yt-dlp"]

    _URL_PATTERNS = [
        r"youtube\.com/watch",
        r"youtu\.be/",
        r"youtube\.com/shorts/",
        r"youtube\.com/live/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Extract transcript from a YouTube video."""
        video_id = self._extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract YouTube video ID from: {url}")

        # Try transcript API first
        try:
            return self._read_transcript_api(video_id, url)
        except Exception as e:
            logger.debug(f"youtube-transcript-api failed: {e}")

        # Fallback to yt-dlp
        try:
            return self._read_ytdlp(video_id, url)
        except Exception as e:
            logger.debug(f"yt-dlp fallback failed: {e}")

        raise RuntimeError(
            f"Could not extract transcript for video {video_id}. "
            "The video may not have captions available."
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """YouTube search requires the paid Data API — not available zero-config."""
        raise SearchNotSupportedError(
            "YouTube search requires a YouTube Data API key, not configured; "
            "use read() with a specific video URL instead"
        )

    def check(self, config: Config) -> ChannelStatus:
        # Check primary backend
        result = probe_python_import("youtube-transcript-api", "youtube_transcript_api")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="youtube-transcript-api",
                message=f"youtube-transcript-api v{result.version}",
            )

        # Check fallback
        yt_result = probe_command("yt-dlp", ["yt-dlp", "--version"])
        if yt_result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="yt-dlp",
                message=f"yt-dlp {yt_result.version}",
            )

        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message="Neither youtube-transcript-api nor yt-dlp available",
        )

    def _read_transcript_api(self, video_id: str, url: str) -> Content:
        """Use youtube-transcript-api for direct transcript extraction."""
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)

        # Build body from transcript segments
        lines = []
        for segment in transcript_list:
            start = segment.get("start", 0)
            text = segment.get("text", "")
            minutes = int(start // 60)
            seconds = int(start % 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        # Also get plain text version
        plain_text = " ".join(s.get("text", "") for s in transcript_list)

        return Content(
            title=f"YouTube Video: {video_id}",
            body="\n".join(lines),
            abstract=plain_text[:500] + "..." if len(plain_text) > 500 else plain_text,
            url=url,
            source_channel=self.name,
            backend="youtube-transcript-api",
            metadata={
                "video_id": video_id,
                "segment_count": len(transcript_list),
            },
        )

    def _read_ytdlp(self, video_id: str, url: str) -> Content:
        """Use yt-dlp to download subtitles."""
        import subprocess
        import tempfile
        import json as _json

        # First get video info
        info_result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, timeout=30,
        )
        info = {}
        if info_result.returncode == 0:
            try:
                info = _json.loads(info_result.stdout)
            except _json.JSONDecodeError:
                pass

        # Download subtitles
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_result = subprocess.run(
                [
                    "yt-dlp",
                    "--write-auto-sub", "--write-sub",
                    "--sub-lang", "en",
                    "--sub-format", "vtt",
                    "--skip-download",
                    "-o", f"{tmpdir}/%(id)s.%(ext)s",
                    url,
                ],
                capture_output=True, text=True, timeout=60,
            )

            # Read the subtitle file
            import glob
            vtt_files = glob.glob(f"{tmpdir}/*.vtt")
            if not vtt_files:
                raise RuntimeError("yt-dlp did not produce subtitle files")

            with open(vtt_files[0], "r", encoding="utf-8") as f:
                vtt_content = f.read()

        # Parse VTT to plain text
        lines = []
        for line in vtt_content.split("\n"):
            line = line.strip()
            if not line or "-->" in line or line.startswith("WEBVTT") or line.startswith("Kind:"):
                continue
            # Remove VTT tags
            clean = re.sub(r"<[^>]+>", "", line)
            if clean:
                lines.append(clean)

        body = "\n".join(lines)

        return Content(
            title=info.get("title", f"YouTube Video: {video_id}"),
            authors=[info.get("uploader", "")],
            body=body,
            url=url,
            source_channel=self.name,
            published_date=info.get("upload_date", ""),
            backend="yt-dlp",
            metadata={
                "video_id": video_id,
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
            },
        )

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        """Extract YouTube video ID from various URL formats."""
        patterns = [
            r"(?:v=|/v/|youtu\.be/|/shorts/|/live/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
