"""
Crossref channel — DOI metadata and citation data.

Backend: Crossref REST API (free, no key, polite pool with email).
Tier: zero-config.
"""

from __future__ import annotations

import re
from urllib.parse import quote

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
from social_dive.http_client import get_client
from social_dive.probe import probe_url


@register_channel
class CrossrefChannel(Channel):
    name = "crossref"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["crossref-api"]

    _API_BASE = "https://api.crossref.org"

    _URL_PATTERNS = [
        r"doi\.org/",
        r"dx\.doi\.org/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Fetch metadata for a DOI from Crossref."""
        doi = self._extract_doi(url)
        if not doi:
            raise ValueError(f"Could not extract DOI from: {url}")

        contact_email = config.get("openalex_email", "noreply@example.com")
        headers = {"User-Agent": f"SocialDive/0.2.0 (mailto:{contact_email})"}

        resp = get_client(config).get(
            f"{self._API_BASE}/works/{quote(doi, safe='/')}",
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        work = resp.json().get("message", {})

        # Parse authors
        authors = []
        for author in work.get("author", []):
            name = f"{author.get('given', '')} {author.get('family', '')}".strip()
            if name:
                authors.append(name)

        # Parse title
        title_list = work.get("title", [])
        title = title_list[0] if title_list else ""

        # Parse abstract
        abstract = work.get("abstract", "")
        if abstract:
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()

        # Build body with metadata
        body_parts = [f"# {title}\n"]
        if authors:
            body_parts.append(f"*{', '.join(authors)}*\n")
        if abstract:
            body_parts.append(f"\n> {abstract}\n")

        body_parts.append(f"\n**DOI:** {doi}")
        body_parts.append(f"**Type:** {work.get('type', 'unknown')}")

        container = work.get("container-title", [])
        if container:
            body_parts.append(f"**Journal:** {container[0]}")

        body_parts.append(f"**Citations:** {work.get('is-referenced-by-count', 0)}")
        body_parts.append(f"**References:** {work.get('references-count', 0)}")

        published = work.get("published-print", work.get("published-online", {}))
        pub_date = ""
        if published and "date-parts" in published:
            parts = published["date-parts"][0]
            pub_date = "-".join(str(p) for p in parts)

        return Content(
            title=title,
            authors=authors,
            abstract=abstract,
            body="\n".join(body_parts),
            url=f"https://doi.org/{doi}",
            source_channel=self.name,
            backend=self.backends[0],
            published_date=pub_date,
            metadata={
                "doi": doi,
                "type": work.get("type", ""),
                "publisher": work.get("publisher", ""),
                "citation_count": work.get("is-referenced-by-count", 0),
                "references_count": work.get("references-count", 0),
                "issn": work.get("ISSN", []),
                "subject": work.get("subject", []),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Crossref for works matching the query."""
        contact_email = config.get("openalex_email", "noreply@example.com")
        headers = {"User-Agent": f"SocialDive/0.2.0 (mailto:{contact_email})"}

        resp = get_client(config).get(
            f"{self._API_BASE}/works",
            params={"query": query, "rows": limit, "sort": "relevance"},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for work in resp.json().get("message", {}).get("items", []):
            title_list = work.get("title", [])
            title = title_list[0] if title_list else "Untitled"
            doi = work.get("DOI", "")

            authors = []
            for author in work.get("author", [])[:5]:
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if name:
                    authors.append(name)

            abstract = work.get("abstract", "")
            if abstract:
                abstract = re.sub(r"<[^>]+>", "", abstract)[:300]

            results.append(
                SearchResult(
                    title=title,
                    url=f"https://doi.org/{doi}" if doi else "",
                    snippet=abstract,
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=authors,
                    score=float(work.get("is-referenced-by-count", 0)),
                    metadata={
                        "doi": doi,
                        "type": work.get("type", ""),
                        "citation_count": work.get("is-referenced-by-count", 0),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("crossref-api", f"{self._API_BASE}/works?query=test&rows=1")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="crossref-api",
                message="Crossref API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"Crossref API unreachable: {result.error}",
        )

    @staticmethod
    def _extract_doi(url: str) -> str | None:
        """Extract DOI from a URL or raw DOI string."""
        # Match DOI pattern: 10.XXXX/anything
        match = re.search(r"(10\.\d{4,}[^\s]+)", url)
        return match.group(1).rstrip("/") if match else None
