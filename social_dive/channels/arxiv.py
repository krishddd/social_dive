"""
arXiv channel — search and read academic papers from arXiv.org.

Backend: ``arxiv`` Python library (official API wrapper).
Tier: zero-config (no API key needed).
"""

from __future__ import annotations

import re
from typing import Any

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
from social_dive.probe import probe_python_import


@register_channel
class ArxivChannel(Channel):
    name = "arxiv"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["arxiv-api"]

    # URL patterns for arXiv
    _URL_PATTERNS = [
        r"arxiv\.org/abs/",
        r"arxiv\.org/pdf/",
        r"arxiv\.org/html/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Fetch paper metadata and abstract from arXiv."""
        import arxiv

        # Extract arXiv ID from URL
        arxiv_id = self._extract_id(url)
        if not arxiv_id:
            raise ValueError(f"Could not extract arXiv ID from URL: {url}")

        client = arxiv.Client()
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(client.results(search))

        if not results:
            raise ValueError(f"No paper found for arXiv ID: {arxiv_id}")

        paper = results[0]

        return Content(
            title=paper.title,
            authors=[str(a) for a in paper.authors],
            abstract=paper.summary,
            body=f"**Abstract:**\n\n{paper.summary}\n\n"
                 f"**Categories:** {', '.join(paper.categories)}\n\n"
                 f"**PDF:** {paper.pdf_url}\n\n"
                 f"**Published:** {paper.published.strftime('%Y-%m-%d') if paper.published else 'Unknown'}\n\n"
                 f"**Updated:** {paper.updated.strftime('%Y-%m-%d') if paper.updated else 'Unknown'}",
            url=paper.entry_id,
            source_channel=self.name,
            backend=self.backends[0],
            published_date=paper.published.isoformat() if paper.published else "",
            metadata={
                "arxiv_id": arxiv_id,
                "categories": paper.categories,
                "pdf_url": str(paper.pdf_url),
                "primary_category": paper.primary_category,
                "comment": paper.comment or "",
                "doi": paper.doi or "",
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search arXiv for papers matching the query."""
        import arxiv

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=limit,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results: list[SearchResult] = []
        for paper in client.results(search):
            results.append(
                SearchResult(
                    title=paper.title,
                    url=paper.entry_id,
                    snippet=paper.summary[:300] + "..." if len(paper.summary) > 300 else paper.summary,
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=[str(a) for a in paper.authors],
                    published_date=paper.published.isoformat() if paper.published else "",
                    metadata={
                        "arxiv_id": self._extract_id(paper.entry_id) or "",
                        "categories": paper.categories,
                        "pdf_url": str(paper.pdf_url),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_python_import("arxiv-api", "arxiv")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="arxiv-api",
                message=f"arxiv library v{result.version}",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"arxiv library not available: {result.error}",
        )

    @staticmethod
    def _extract_id(url: str) -> str | None:
        """Extract arXiv ID from various URL formats."""
        # Matches: 2401.12345, 2401.12345v2, hep-ph/0601001
        patterns = [
            r"(\d{4}\.\d{4,5}(?:v\d+)?)",
            r"([\w-]+/\d{7}(?:v\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
