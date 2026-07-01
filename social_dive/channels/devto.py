"""
DEV.to channel — read and browse articles from DEV.to (Forem API).

Backend: Forem REST API (free, no key for public articles).
Tier: zero-config.
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
class DevtoChannel(Channel):
    name = "devto"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["forem-api"]

    _API_BASE = "https://dev.to/api"
    _HEADERS = {"Accept": "application/vnd.forem.api-v1+json"}

    _URL_PATTERNS = [
        r"dev\.to/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a DEV.to article by its URL."""
        # Try to get article by path
        path = self._extract_path(url)
        if not path:
            raise ValueError(f"Could not extract DEV.to article path from: {url}")

        # Use the articles endpoint with a path lookup
        resp = httpx.get(
            f"{self._API_BASE}/articles/{path}",
            headers=self._HEADERS,
            timeout=15.0,
            follow_redirects=True,
        )

        # If path lookup fails, try searching by URL
        if resp.status_code != 200:
            resp = httpx.get(
                f"{self._API_BASE}/articles",
                params={"url": url},
                headers=self._HEADERS,
                timeout=15.0,
            )
            resp.raise_for_status()
            articles = resp.json()
            if not articles:
                raise ValueError(f"No article found at: {url}")
            article = articles[0]
        else:
            article = resp.json()

        return Content(
            title=article.get("title", ""),
            authors=[article.get("user", {}).get("name", "")],
            abstract=article.get("description", ""),
            body=article.get("body_markdown", article.get("body_html", "")),
            url=article.get("url", url),
            source_channel=self.name,
            published_date=article.get("published_at", ""),
            metadata={
                "tags": article.get("tags", []),
                "positive_reactions_count": article.get("positive_reactions_count", 0),
                "comments_count": article.get("comments_count", 0),
                "reading_time_minutes": article.get("reading_time_minutes", 0),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search DEV.to articles."""
        resp = httpx.get(
            f"{self._API_BASE}/articles",
            params={"tag": query, "per_page": limit, "top": 30},
            headers=self._HEADERS,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for article in resp.json()[:limit]:
            results.append(
                SearchResult(
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    snippet=article.get("description", ""),
                    source_channel=self.name,
                    authors=[article.get("user", {}).get("name", "")],
                    published_date=article.get("published_at", ""),
                    score=float(article.get("positive_reactions_count", 0)),
                    metadata={
                        "tags": article.get("tag_list", []),
                        "reading_time_minutes": article.get("reading_time_minutes", 0),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("forem-api", f"{self._API_BASE}/articles?per_page=1")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="forem-api",
                message="DEV.to Forem API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"DEV.to API unreachable: {result.error}",
        )

    @staticmethod
    def _extract_path(url: str) -> str | None:
        """Extract username/slug from a DEV.to URL."""
        match = re.search(r"dev\.to/(.+?)(?:\?|#|$)", url)
        return match.group(1) if match else None
