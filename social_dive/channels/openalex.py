"""
OpenAlex channel — search scholarly works via the OpenAlex API.

Backend: OpenAlex REST API (free daily quota with API key).
Tier: needs-key (free API key for daily budget).
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
class OpenAlexChannel(Channel):
    name = "openalex"
    tier = ChannelTier.NEEDS_KEY
    backends = ["openalex-api"]

    _API_BASE = "https://api.openalex.org"

    _URL_PATTERNS = [
        r"openalex\.org/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a work from OpenAlex."""
        work_id = self._extract_work_id(url)
        if not work_id:
            raise ValueError(f"Could not extract OpenAlex work ID from: {url}")

        params = self._make_params(config)
        resp = httpx.get(
            f"{self._API_BASE}/works/{work_id}",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        work = resp.json()

        title = work.get("title", "")
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in work.get("authorships", [])
        ]
        abstract = ""
        if work.get("abstract_inverted_index"):
            abstract = self._reconstruct_abstract(work["abstract_inverted_index"])

        body = f"# {title}\n\n"
        if authors:
            body += f"*{', '.join(authors[:10])}*\n\n"
        if abstract:
            body += f"> {abstract}\n\n"

        body += f"**Year:** {work.get('publication_year', 'Unknown')}\n"
        body += f"**Citations:** {work.get('cited_by_count', 0)}\n"
        body += f"**Type:** {work.get('type', 'Unknown')}\n"

        source = work.get("primary_location", {}).get("source", {})
        if source:
            body += f"**Source:** {source.get('display_name', '')}\n"

        doi = work.get("doi", "")
        if doi:
            body += f"**DOI:** {doi}\n"

        return Content(
            title=title,
            authors=authors,
            abstract=abstract,
            body=body,
            url=work.get("id", url),
            source_channel=self.name,
            backend=self.backends[0],
            published_date=str(work.get("publication_date", "")),
            metadata={
                "openalex_id": work.get("id", ""),
                "doi": doi,
                "citation_count": work.get("cited_by_count", 0),
                "type": work.get("type", ""),
                "is_oa": work.get("open_access", {}).get("is_oa", False),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search OpenAlex for works."""
        params = self._make_params(config)
        params["search"] = query
        params["per_page"] = limit

        resp = httpx.get(
            f"{self._API_BASE}/works",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for work in resp.json().get("results", []):
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])[:5]
            ]

            abstract = ""
            if work.get("abstract_inverted_index"):
                abstract = self._reconstruct_abstract(work["abstract_inverted_index"])

            results.append(
                SearchResult(
                    title=work.get("title", ""),
                    url=work.get("id", ""),
                    snippet=abstract[:300] + "..." if len(abstract) > 300 else abstract,
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=authors,
                    published_date=str(work.get("publication_date", "")),
                    score=float(work.get("cited_by_count", 0)),
                    metadata={
                        "openalex_id": work.get("id", ""),
                        "doi": work.get("doi", ""),
                        "citation_count": work.get("cited_by_count", 0),
                        "is_oa": work.get("open_access", {}).get("is_oa", False),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("openalex-api", f"{self._API_BASE}/works?search=test&per_page=1")
        if result.ok:
            has_key = bool(config.get("openalex_api_key"))
            key_note = "(with key)" if has_key else "(no key, limited daily quota)"
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="openalex-api",
                message=f"OpenAlex API reachable {key_note}",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"OpenAlex API unreachable: {result.error}",
        )

    def _make_params(self, config: Config) -> dict:
        params: dict = {}
        email = config.get("openalex_email")
        if email:
            params["mailto"] = email
        api_key = config.get("openalex_api_key")
        if api_key:
            params["api_key"] = api_key
        return params

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        """Reconstruct abstract text from OpenAlex's inverted index format."""
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(word for _, word in word_positions)

    @staticmethod
    def _extract_work_id(url: str) -> str | None:
        # OpenAlex IDs: W1234567890 or full URLs
        match = re.search(r"(W\d+)", url)
        if match:
            return match.group(1)
        return url
