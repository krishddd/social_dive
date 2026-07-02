"""
Hacker News channel — read stories/comments and search via Algolia.

Backends:
  1. Algolia Search API (search + comment threads)
  2. Firebase API (individual items by ID)

Tier: zero-config (no API key needed).
"""

from __future__ import annotations

import re

import httpx
from loguru import logger

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel
from social_dive.probe import probe_url


@register_channel
class HackerNewsChannel(Channel):
    name = "hacker_news"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["algolia-api", "firebase-api"]

    _ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
    _FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"

    _URL_PATTERNS = [
        r"news\.ycombinator\.com",
        r"hacker-news\.firebaseio\.com",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a Hacker News story and its top comments."""
        item_id = self._extract_item_id(url)
        if not item_id:
            raise ValueError(f"Could not extract HN item ID from: {url}")

        # Get the story from Firebase
        resp = httpx.get(
            f"{self._FIREBASE_BASE}/item/{item_id}.json",
            timeout=15.0,
        )
        resp.raise_for_status()
        story = resp.json()

        if not story:
            raise ValueError(f"HN item {item_id} not found")

        # Get comments via Algolia
        comments = self._get_comments_algolia(item_id)

        title = story.get("title", "")
        story_url = story.get("url", url)
        by = story.get("by", "unknown")
        score = story.get("score", 0)
        text = story.get("text", "")

        body_parts = [f"# {title}\n\n*by {by} · {score} points*\n"]
        if text:
            body_parts.append(f"\n{text}\n")
        if story_url != url:
            body_parts.append(f"\n**Link:** {story_url}\n")

        if comments:
            body_parts.append("\n---\n\n## Comments\n\n")
            for c in comments[:30]:  # Top 30 comments
                author = c.get("author", "anon")
                comment_text = c.get("comment_text", "")
                if comment_text:
                    # Strip HTML
                    clean = re.sub(r"<[^>]+>", "", comment_text).strip()
                    body_parts.append(f"**{author}:** {clean}\n\n")

        return Content(
            title=title,
            authors=[by],
            body="".join(body_parts),
            url=url,
            source_channel=self.name,
            backend="firebase-api",
            metadata={
                "item_id": item_id,
                "score": score,
                "comment_count": story.get("descendants", 0),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Hacker News stories via Algolia."""
        resp = httpx.get(
            f"{self._ALGOLIA_BASE}/search",
            params={
                "query": query,
                "tags": "story",
                "hitsPerPage": limit,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for hit in data.get("hits", []):
            fallback_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            results.append(
                SearchResult(
                    title=hit.get("title", ""),
                    url=hit.get("url") or fallback_url,
                    snippet=hit.get("story_text", "")[:300] if hit.get("story_text") else "",
                    source_channel=self.name,
                    backend="algolia-api",
                    authors=[hit.get("author", "")],
                    published_date=hit.get("created_at", ""),
                    score=float(hit.get("points", 0)),
                    metadata={
                        "hn_id": hit.get("objectID", ""),
                        "points": hit.get("points", 0),
                        "num_comments": hit.get("num_comments", 0),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("algolia-api", f"{self._ALGOLIA_BASE}/search?query=test&hitsPerPage=1")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="algolia-api",
                message="Algolia HN API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"HN APIs unreachable: {result.error}",
        )

    def _get_comments_algolia(self, story_id: str) -> list[dict]:
        """Fetch comments for a story via Algolia (much faster than recursive Firebase)."""
        try:
            resp = httpx.get(
                f"{self._ALGOLIA_BASE}/search",
                params={
                    "tags": f"comment,story_{story_id}",
                    "hitsPerPage": 50,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            hits: list[dict] = resp.json().get("hits", [])
            return hits
        except Exception as e:
            logger.debug(f"Failed to fetch HN comments: {e}")
            return []

    @staticmethod
    def _extract_item_id(url: str) -> str | None:
        match = re.search(r"id=(\d+)", url)
        return match.group(1) if match else None
