"""
DOI Resolver channel — resolve a DOI to full-text content via multi-source fallback.

This channel chains through multiple sources to find the best full-text
version of a paper given its DOI. The chain order is driven by
``ordered_backends()`` (default: Europe PMC → Unpaywall → Crossref), so a user
can force a preferred source with the ``doi_resolver_backend`` config key:

  1. Europe PMC — open-access full text
  2. Unpaywall  — OA link discovery (fetched via the web channel)
  3. Crossref   — metadata + abstract (the guaranteed final fallback)

Tier: zero-config.
"""

from __future__ import annotations

import re
from urllib.parse import quote

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
from social_dive.http_client import get_client


@register_channel
class DOIResolverChannel(Channel):
    name = "doi_resolver"
    tier = ChannelTier.ZERO_CONFIG
    # Ordered by preference: full text first, metadata-only Crossref last as
    # the guaranteed fallback. ordered_backends() lets a user reprioritize.
    backends = ["europepmc", "unpaywall", "crossref"]

    _EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    _URL_PATTERNS = [
        r"^10\.\d{4,}/",  # Raw DOI string
    ]

    def can_handle(self, url: str) -> bool:
        """Handles raw DOI strings (not full URLs — Crossref channel handles those)."""
        return bool(re.match(r"^10\.\d{4,}/", url))

    def read(self, url: str, config: Config) -> Content:
        """Resolve a DOI to content, trying each source in backend order.

        Each source returns ``Content`` if it produced a usable result or
        ``None`` to defer to the next; Crossref (metadata) never returns
        ``None``, so as long as it's in the chain a result is guaranteed.
        """
        doi = url.strip()
        sources = {
            "europepmc": self._try_europepmc,
            "unpaywall": self._try_unpaywall,
            "crossref": self._try_crossref,
        }

        last_error: Exception | None = None
        for backend in self.ordered_backends(config):
            source = sources.get(backend)
            if source is None:
                continue
            try:
                content = source(doi, config)
            except Exception as e:  # noqa: BLE001 — try the next source
                logger.debug(f"DOI resolver: '{backend}' failed for {doi}: {e}")
                last_error = e
                continue
            if content is not None:
                return content

        if last_error is not None:
            raise last_error
        raise ValueError(f"Could not resolve DOI: {doi}")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """DOI resolver takes a specific DOI, not a query — it has no search index."""
        raise SearchNotSupportedError(
            "DOI resolver has no search index; use the 'crossref' or "
            "'semantic_scholar' channels to search, then resolve a DOI here"
        )

    def check(self, config: Config) -> ChannelStatus:
        order = " → ".join(self.ordered_backends(config))
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.OK,
            tier=self.tier,
            active_backend="multi-source",
            message=f"DOI resolver ({order})",
        )

    # -- per-source resolvers (return Content, or None to defer) -------------

    def _try_europepmc(self, doi: str, config: Config) -> Content | None:
        content = self._read_europepmc(doi, config)
        # A thin abstract-only body isn't worth stopping the chain for.
        if content.body and len(content.body) > 200:
            return content
        return None

    def _try_unpaywall(self, doi: str, config: Config) -> Content | None:
        oa_url = self._find_oa_url(doi, config)
        if not oa_url:
            return None
        # Delegate to the web channel for the actual fetch.
        from social_dive.channels.web import WebChannel

        content = WebChannel().read(oa_url, config)
        content.source_channel = self.name
        content.backend = "unpaywall"
        content.metadata["doi"] = doi
        content.metadata["oa_source"] = "unpaywall"
        return content

    def _try_crossref(self, doi: str, config: Config) -> Content:
        from social_dive.channels.crossref import CrossrefChannel

        content = CrossrefChannel().read(f"https://doi.org/{doi}", config)
        content.source_channel = self.name
        content.backend = "crossref"
        return content

    def _read_europepmc(self, doi: str, config: Config) -> Content:
        """Try to get full text from Europe PMC."""
        client = get_client(config)
        resp = client.get(
            f"{self._EUROPEPMC_BASE}/search",
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
                ft_resp = client.get(
                    f"{self._EUROPEPMC_BASE}/{pmcid}/fullTextXML",
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
        resp = get_client(config).get(
            f"https://api.unpaywall.org/v2/{quote(doi, safe='/')}",
            params={"email": email},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        best_oa = data.get("best_oa_location", {})
        if best_oa:
            oa_url: str | None = best_oa.get("url_for_pdf") or best_oa.get("url")
            return oa_url
        return None
