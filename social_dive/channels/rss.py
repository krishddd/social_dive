"""
RSS / Atom feed channel.

Backend: ``feedparser`` Python library.
Tier: zero-config.
"""

from __future__ import annotations

import re

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
from social_dive.probe import probe_python_import


@register_channel
class RSSChannel(Channel):
    name = "rss"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["feedparser"]

    _URL_PATTERNS = [
        r"/rss",
        r"/feed",
        r"/atom",
        r"\.xml$",
        r"\.rss$",
        r"feeds\.",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Parse an RSS/Atom feed and return its entries as structured content."""
        import feedparser

        feed = feedparser.parse(url, agent="SocialDive/0.2.0")

        if feed.bozo and not feed.entries:
            raise ValueError(f"Failed to parse feed at {url}: {feed.bozo_exception}")

        # Build body from entries
        entries_text = []
        for entry in feed.entries[:50]:  # Cap at 50 entries
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "")

            # Strip HTML from summary
            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()
            if len(summary_clean) > 500:
                summary_clean = summary_clean[:500] + "..."

            entries_text.append(
                f"### {title}\n"
                f"*{published}*\n"
                f"{summary_clean}\n"
                f"[Read more]({link})\n"
            )

        feed_title = feed.feed.get("title", "RSS Feed")
        feed_desc = feed.feed.get("description", "")

        return Content(
            title=feed_title,
            body=f"# {feed_title}\n\n{feed_desc}\n\n" + "\n---\n\n".join(entries_text),
            url=url,
            source_channel=self.name,
            backend=self.backends[0],
            metadata={
                "feed_type": feed.version or "unknown",
                "entry_count": len(feed.entries),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """RSS has no search index — a feed URL must be read directly."""
        raise SearchNotSupportedError(
            "RSS/Atom feeds have no search index; use read() with a specific feed URL"
        )

    def check(self, config: Config) -> ChannelStatus:
        result = probe_python_import("feedparser", "feedparser")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="feedparser",
                message=f"feedparser v{result.version}",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"feedparser not available: {result.error}",
        )
