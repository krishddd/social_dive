"""
Europe PMC channel — open-access biomedical literature.

Backend: Europe PMC REST API (free, no key).
Tier: needs-key (technically zero-config, but email recommended).
"""

from __future__ import annotations

import re

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
class EuropePMCChannel(Channel):
    name = "europe_pmc"
    tier = ChannelTier.NEEDS_KEY
    backends = ["europepmc-api"]

    _API_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    _URL_PATTERNS = [
        r"europepmc\.org/",
        r"ebi\.ac\.uk/europepmc/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a paper from Europe PMC."""
        pmcid = self._extract_id(url)
        if not pmcid:
            raise ValueError(f"Could not extract PMC ID from: {url}")

        client = get_client(config)
        resp = client.get(
            f"{self._API_BASE}/search",
            params={
                "query": f"(EXT_ID:{pmcid})",
                "format": "json",
                "resultType": "core",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        results = resp.json().get("resultList", {}).get("result", [])

        if not results:
            raise ValueError(f"No Europe PMC result for: {pmcid}")

        paper = results[0]

        # Try full text
        body = paper.get("abstractText", "")
        pmc_id = paper.get("pmcid", "")
        if pmc_id:
            try:
                ft_resp = client.get(
                    f"{self._API_BASE}/{pmc_id}/fullTextXML",
                    timeout=20.0,
                )
                if ft_resp.status_code == 200:
                    body = re.sub(r"<[^>]+>", " ", ft_resp.text)
                    body = re.sub(r"\s+", " ", body).strip()
                    body = body[:15000]  # Cap
            except Exception:
                pass

        authors = [
            f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
            for a in paper.get("authorList", {}).get("author", [])
        ]

        return Content(
            title=paper.get("title", ""),
            authors=authors,
            abstract=paper.get("abstractText", ""),
            body=body,
            url=f"https://europepmc.org/article/{paper.get('source', 'MED')}/{paper.get('id', '')}",
            source_channel=self.name,
            backend=self.backends[0],
            published_date=paper.get("firstPublicationDate", ""),
            metadata={
                "pmcid": pmc_id,
                "pmid": paper.get("pmid", ""),
                "doi": paper.get("doi", ""),
                "source": paper.get("source", ""),
                "citation_count": paper.get("citedByCount", 0),
                "is_open_access": paper.get("isOpenAccess", "N") == "Y",
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Europe PMC."""
        resp = get_client(config).get(
            f"{self._API_BASE}/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": limit,
                "resultType": "core",
            },
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for paper in resp.json().get("resultList", {}).get("result", []):
            authors = [
                f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
                for a in paper.get("authorList", {}).get("author", [])[:5]
            ]

            article_url = (
                f"https://europepmc.org/article/{paper.get('source', 'MED')}/{paper.get('id', '')}"
            )
            results.append(
                SearchResult(
                    title=paper.get("title", ""),
                    url=article_url,
                    snippet=(paper.get("abstractText", "") or "")[:300],
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=authors,
                    published_date=paper.get("firstPublicationDate", ""),
                    score=float(paper.get("citedByCount", 0)),
                    metadata={
                        "pmid": paper.get("pmid", ""),
                        "doi": paper.get("doi", ""),
                        "is_open_access": paper.get("isOpenAccess", "N") == "Y",
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        probe_target = f"{self._API_BASE}/search?query=test&format=json&pageSize=1"
        result = probe_url("europepmc-api", probe_target)
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="europepmc-api",
                message="Europe PMC API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"Europe PMC API unreachable: {result.error}",
        )

    @staticmethod
    def _extract_id(url: str) -> str | None:
        # PMC IDs or PMIDs from URLs
        match = re.search(r"(PMC\d+|\d{5,12})", url)
        return match.group(1) if match else None
