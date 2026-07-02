"""
DOI Resolver channel — resolve a DOI to full-text content via multi-source fallback.

This channel chains through multiple sources to find the best full-text
version of a paper given its DOI:
  1. Crossref (metadata + abstract)
  2. Europe PMC (open-access full text)
  3. Unpaywall (OA link discovery)

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
    SearchNotSupportedError,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class DOIResolverChannel(Channel):
    name = "doi_resolver"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["crossref", "europepmc", "unpaywall"]

    _URL_PATTERNS = [
        r"^10\.\d{4,}/",  # Raw DOI string
    ]

    def can_handle(self, url: str) -> bool:
        """Handles raw DOI strings (not full URLs — Crossref channel handles those)."""
        return bool(re.match(r"^10\.\d{4,}/", url))

    def read(self, url: str, config: Config) -> Content:
        """Resolve a DOI to full-text content via multi-source fallback."""
        doi = url.strip()

        # 1. Try Europe PMC for open-access full text
        try:
            content = self._read_europepmc(doi)
            if content.body and len(content.body) > 200:
                return content
        except Exception as e:
            logger.debug(f"Europe PMC lookup failed for {doi}: {e}")

        # 2. Try Unpaywall for OA links
        try:
            oa_url = self._find_oa_url(doi, config)
            if oa_url:
                # Delegate to web channel for the actual fetch
                from social_dive.channels.web import WebChannel
                web = WebChannel()
                content = web.read(oa_url, config)
                content.source_channel = self.name
                content.backend = "unpaywall"
                content.metadata["doi"] = doi
                content.metadata["oa_source"] = "unpaywall"
                return content
        except Exception as e:
            logger.debug(f"Unpaywall lookup failed for {doi}: {e}")

        # 3. Fall back to Crossref metadata
        from social_dive.channels.crossref import CrossrefChannel
        crossref = CrossrefChannel()
        content = crossref.read(f"https://doi.org/{doi}", config)
        content.source_channel = self.name
        content.backend = "crossref"
        return content

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """DOI resolver takes a specific DOI, not a query — it has no search index."""
        raise SearchNotSupportedError(
            "DOI resolver has no search index; use the 'crossref' or "
            "'semantic_scholar' channels to search, then resolve a DOI here"
        )

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.OK,
            tier=self.tier,
            active_backend="multi-source",
            message="DOI resolver (Crossref → Europe PMC → Unpaywall)",
        )

    def _read_europepmc(self, doi: str) -> Content:
        """Try to get full text from Europe PMC."""
        # Search for the paper by DOI
        resp = httpx.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={
                "query": f"DOI:{doi}",
                "format": "json",
                "resultType": "core",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        results = resp.json().get("resultList", {}).get("result", [])

        if not results:
            raise ValueError(f"No Europe PMC result for DOI: {doi}")

        paper = results[0]
        pmcid = paper.get("pmcid", "")

        body = ""
        if pmcid:
            # Try to get full text
            try:
                ft_resp = httpx.get(
                    f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                    timeout=20.0,
                )
                if ft_resp.status_code == 200:
                    # Strip XML tags for now
                    body = re.sub(r"<[^>]+>", " ", ft_resp.text)
                    body = re.sub(r"\s+", " ", body).strip()
            except Exception:
                pass

        if not body:
            body = paper.get("abstractText", "")

        return Content(
            title=paper.get("title", ""),
            authors=[
                f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
                for a in paper.get("authorList", {}).get("author", [])
            ],
            abstract=paper.get("abstractText", ""),
            body=body,
            url=f"https://doi.org/{doi}",
            source_channel=self.name,
            backend="europepmc",
            published_date=paper.get("firstPublicationDate", ""),
            metadata={
                "doi": doi,
                "pmcid": pmcid,
                "pmid": paper.get("pmid", ""),
                "source": paper.get("source", ""),
            },
        )

    def _find_oa_url(self, doi: str, config: Config) -> str | None:
        """Use Unpaywall API to find an open-access URL."""
        email = config.get("openalex_email", "social-dive@example.com")
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{quote(doi, safe='/')}",
            params={"email": email},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        best_oa = data.get("best_oa_location", {})
        if best_oa:
            return best_oa.get("url_for_pdf") or best_oa.get("url")
        return None
