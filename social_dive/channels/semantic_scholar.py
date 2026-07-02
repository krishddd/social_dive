"""
Semantic Scholar channel — search and read academic papers.

Backend: Semantic Scholar Graph API (free, optional API key).
Tier: needs-key (optional, for higher rate limits).
"""

from __future__ import annotations

import re

import httpx

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
class SemanticScholarChannel(Channel):
    name = "semantic_scholar"
    tier = ChannelTier.NEEDS_KEY
    backends = ["s2-api"]

    _API_BASE = "https://api.semanticscholar.org/graph/v1"
    _FIELDS = (
        "title,abstract,authors,year,citationCount,referenceCount,url,externalIds,"
        "publicationDate,venue"
    )

    _URL_PATTERNS = [
        r"semanticscholar\.org/paper/",
        r"api\.semanticscholar\.org/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read paper details from Semantic Scholar."""
        paper_id = self._extract_paper_id(url)
        if not paper_id:
            raise ValueError(f"Could not extract S2 paper ID from: {url}")

        headers = self._make_headers(config)

        resp = httpx.get(
            f"{self._API_BASE}/paper/{paper_id}",
            params={"fields": self._FIELDS},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        paper = resp.json()

        authors = [a.get("name", "") for a in paper.get("authors", [])]
        abstract = paper.get("abstract", "") or ""

        body = f"# {paper.get('title', '')}\n\n"
        if authors:
            body += f"*{', '.join(authors)}*\n\n"
        if abstract:
            body += f"> {abstract}\n\n"
        body += f"**Year:** {paper.get('year', 'Unknown')}\n"
        body += f"**Venue:** {paper.get('venue', 'Unknown')}\n"
        body += f"**Citations:** {paper.get('citationCount', 0)}\n"
        body += f"**References:** {paper.get('referenceCount', 0)}\n"

        ext_ids = paper.get("externalIds", {})
        if ext_ids.get("DOI"):
            body += f"**DOI:** {ext_ids['DOI']}\n"
        if ext_ids.get("ArXiv"):
            body += f"**arXiv:** {ext_ids['ArXiv']}\n"

        return Content(
            title=paper.get("title", ""),
            authors=authors,
            abstract=abstract,
            body=body,
            url=paper.get("url", url),
            source_channel=self.name,
            backend=self.backends[0],
            published_date=paper.get("publicationDate", ""),
            metadata={
                "s2_id": paper.get("paperId", ""),
                "citation_count": paper.get("citationCount", 0),
                "reference_count": paper.get("referenceCount", 0),
                "external_ids": ext_ids,
                "venue": paper.get("venue", ""),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Semantic Scholar for papers."""
        headers = self._make_headers(config)

        resp = httpx.get(
            f"{self._API_BASE}/paper/search",
            params={
                "query": query,
                "fields": self._FIELDS,
                "limit": limit,
            },
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for paper in resp.json().get("data", []):
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            abstract = paper.get("abstract", "") or ""

            results.append(
                SearchResult(
                    title=paper.get("title", ""),
                    url=paper.get("url", ""),
                    snippet=abstract[:300] + "..." if len(abstract) > 300 else abstract,
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=authors,
                    published_date=paper.get("publicationDate", ""),
                    score=float(paper.get("citationCount", 0)),
                    metadata={
                        "s2_id": paper.get("paperId", ""),
                        "citation_count": paper.get("citationCount", 0),
                        "year": paper.get("year"),
                        "venue": paper.get("venue", ""),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("s2-api", f"{self._API_BASE}/paper/search?query=test&limit=1")
        if result.ok:
            has_key = bool(config.get("semantic_scholar_api_key"))
            key_note = "(with API key)" if has_key else "(no key, lower rate limits)"
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="s2-api",
                message=f"S2 API reachable {key_note}",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"S2 API unreachable: {result.error}",
        )

    def _make_headers(self, config: Config) -> dict[str, str]:
        headers = {"User-Agent": "SocialDive/0.1.0"}
        key = config.get("semantic_scholar_api_key")
        if key:
            headers["x-api-key"] = key
        return headers

    @staticmethod
    def _extract_paper_id(url: str) -> str | None:
        # S2 URLs: /paper/<hex_id> or /paper/<slug>/<hex_id>
        match = re.search(r"paper/(?:.*?/)?([a-f0-9]{40})", url)
        if match:
            return match.group(1)
        # Also handle raw S2 IDs or DOIs
        if re.match(r"^[a-f0-9]{40}$", url):
            return url
        return url  # Let the API try to resolve it
