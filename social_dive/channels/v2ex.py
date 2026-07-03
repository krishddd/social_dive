"""
V2EX channel — Chinese developer forum.

Reads a topic via V2EX's public JSON API (no auth). V2EX has no public search
API, so search is not supported here.

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
from social_dive.http_client import get_client
from social_dive.probe import probe_url


@register_channel
class V2EXChannel(Channel):
    name = "v2ex"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["v2ex-api"]

    _API_TOPIC = "https://www.v2ex.com/api/topics/show.json"

    _URL_PATTERNS = [r"(?:^|//)(?:www\.)?v2ex\.com/t/"]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        topic_id = self._extract_id(url)
        if not topic_id:
            raise ValueError(f"Could not extract V2EX topic id from: {url}")

        resp = get_client(config).get(self._API_TOPIC, params={"id": topic_id}, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            raise ValueError(f"No V2EX topic found for id: {topic_id}")

        topic = data[0]
        author = topic.get("member", {}).get("username", "")
        return Content(
            title=topic.get("title", ""),
            authors=[author] if author else [],
            body=topic.get("content", "") or topic.get("content_rendered", ""),
            url=topic.get("url", url),
            source_channel=self.name,
            backend=self.backends[0],
            metadata={
                "topic_id": topic_id,
                "node": topic.get("node", {}).get("name", ""),
                "replies": topic.get("replies", 0),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        raise SearchNotSupportedError(
            "V2EX has no public search API; read a specific topic URL instead"
        )

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("v2ex-api", f"{self._API_TOPIC}?id=1")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend=self.backends[0],
                message="V2EX API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"V2EX API unreachable: {result.error}",
        )

    @staticmethod
    def _extract_id(url: str) -> str | None:
        match = re.search(r"/t/(\d+)", url)
        return match.group(1) if match else None
