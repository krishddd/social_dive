"""
Exa search channel — neural web search built for agents.

A search-only channel (it discovers URLs; it doesn't read a specific one), so
``can_handle`` is always False and it participates in ``search`` but not read
dispatch. Needs a free-ish Exa API key (``exa_api_key``).

Tier: needs-key.
"""

from __future__ import annotations

import httpx

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

_API_URL = "https://api.exa.ai/search"


@register_channel
class ExaSearchChannel(Channel):
    name = "exa_search"
    tier = ChannelTier.NEEDS_KEY
    backends = ["exa-api"]

    def can_handle(self, url: str) -> bool:
        # Search-only: never claims a URL for reading.
        return False

    def read(self, url: str, config: Config) -> Content:
        raise ValueError("exa_search is search-only; use it via `search`")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        key = config.get("exa_api_key")
        if not key:
            raise SearchNotSupportedError(
                "Exa search needs an API key — set it with "
                "`social-dive configure exa_api_key <key>`"
            )
        resp = httpx.post(
            _API_URL,
            headers={"x-api-key": str(key), "Content-Type": "application/json"},
            json={"query": query, "numResults": limit, "contents": {"highlights": True}},
            timeout=20.0,
        )
        resp.raise_for_status()
        results: list[SearchResult] = []
        for item in resp.json().get("results", []):
            highlights = item.get("highlights") or []
            snippet = highlights[0] if highlights else (item.get("text", "") or "")[:300]
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=snippet,
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=[item.get("author")] if item.get("author") else [],
                    published_date=item.get("publishedDate", ""),
                    score=float(item.get("score", 0) or 0),
                )
            )
        return results

    def check(self, config: Config) -> ChannelStatus:
        if config.get("exa_api_key"):
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend=self.backends[0],
                message="Exa API key configured",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.WARN,
            tier=self.tier,
            message="No Exa API key — set 'exa_api_key' to enable web search",
        )
