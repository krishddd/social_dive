"""
Wikipedia channel — read and search Wikipedia articles.

Backend: Wikipedia REST API (free, no key).
Tier: zero-config.
"""

from __future__ import annotations

import re
from urllib.parse import quote

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
class WikipediaChannel(Channel):
    name = "wikipedia"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["rest-api"]

    _API_BASE = "https://en.wikipedia.org/api/rest_v1"
    _ACTION_API = "https://en.wikipedia.org/w/api.php"

    _URL_PATTERNS = [
        r"(?:\w+\.)?wikipedia\.org/wiki/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a Wikipedia article."""
        title = self._extract_title(url)
        if not title:
            raise ValueError(f"Could not extract Wikipedia article title from: {url}")

        # Get article summary
        resp = httpx.get(
            f"{self._API_BASE}/page/summary/{quote(title)}",
            timeout=15.0,
            headers={"User-Agent": "SocialDive/0.1.0"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        summary_data = resp.json()

        # Get mobile HTML (cleaner than full HTML)
        try:
            html_resp = httpx.get(
                f"{self._API_BASE}/page/mobile-html/{quote(title)}",
                timeout=15.0,
                headers={"User-Agent": "SocialDive/0.1.0"},
                follow_redirects=True,
            )
            html_resp.raise_for_status()
            # Strip HTML to plain text for now
            body_html = html_resp.text
            body_text = re.sub(r"<[^>]+>", " ", body_html)
            body_text = re.sub(r"\s+", " ", body_text).strip()
        except Exception:
            body_text = summary_data.get("extract", "")

        return Content(
            title=summary_data.get("title", title),
            abstract=summary_data.get("extract", ""),
            body=body_text[:10000],  # Cap to avoid enormous articles
            url=summary_data.get("content_urls", {}).get("desktop", {}).get("page", url),
            source_channel=self.name,
            backend=self.backends[0],
            metadata={
                "pageid": summary_data.get("pageid"),
                "description": summary_data.get("description", ""),
                "thumbnail": summary_data.get("thumbnail", {}).get("source", ""),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Wikipedia articles."""
        resp = httpx.get(
            self._ACTION_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
                "utf8": 1,
            },
            timeout=15.0,
            headers={"User-Agent": "SocialDive/0.1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
            results.append(
                SearchResult(
                    title=title,
                    url=f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                    snippet=snippet,
                    source_channel=self.name,
                    backend=self.backends[0],
                    metadata={"pageid": item.get("pageid")},
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("rest-api", f"{self._API_BASE}/page/summary/Python_(programming_language)")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="rest-api",
                message="Wikipedia REST API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"Wikipedia API unreachable: {result.error}",
        )

    @staticmethod
    def _extract_title(url: str) -> str | None:
        match = re.search(r"wikipedia\.org/wiki/(.+?)(?:\?|#|$)", url)
        if match:
            return match.group(1).replace("_", " ")
        return None
