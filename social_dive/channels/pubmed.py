"""
PubMed channel — search biomedical literature via NCBI E-utilities.

Backend: Biopython ``Bio.Entrez`` (official NCBI E-utilities wrapper).
Tier: needs-key (NCBI API key, free, increases rate from 3→10 req/sec).
"""

from __future__ import annotations

import re

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
class PubMedChannel(Channel):
    name = "pubmed"
    tier = ChannelTier.NEEDS_KEY
    backends = ["biopython-entrez"]

    _URL_PATTERNS = [
        r"ncbi\.nlm\.nih\.gov/pubmed/",
        r"pubmed\.ncbi\.nlm\.nih\.gov/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Fetch article details from PubMed."""
        from Bio import Entrez, Medline

        pmid = self._extract_pmid(url)
        if not pmid:
            raise ValueError(f"Could not extract PMID from: {url}")

        self._configure_entrez(config)

        handle = Entrez.efetch(db="pubmed", id=pmid, rettype="medline", retmode="text")
        records = list(Medline.parse(handle))
        handle.close()

        if not records:
            raise ValueError(f"No PubMed record found for PMID: {pmid}")

        record = records[0]
        title = record.get("TI", "")
        authors = record.get("AU", [])
        abstract = record.get("AB", "")
        journal = record.get("JT", "")
        pub_date = record.get("DP", "")

        body = f"# {title}\n\n"
        if authors:
            body += f"*{', '.join(authors)}*\n\n"
        if journal:
            body += f"**Journal:** {journal}\n"
        body += f"**Date:** {pub_date}\n"
        body += f"**PMID:** {pmid}\n\n"
        if abstract:
            body += f"## Abstract\n\n{abstract}\n"

        mesh = record.get("MH", [])
        if mesh:
            body += f"\n**MeSH Terms:** {', '.join(mesh)}\n"

        doi = record.get("AID", [])
        doi_str = ""
        for aid in doi:
            if "[doi]" in aid:
                doi_str = aid.replace(" [doi]", "")
                break

        return Content(
            title=title,
            authors=authors,
            abstract=abstract,
            body=body,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            source_channel=self.name,
            backend=self.backends[0],
            published_date=pub_date,
            metadata={
                "pmid": pmid,
                "journal": journal,
                "doi": doi_str,
                "mesh_terms": mesh,
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search PubMed for articles."""
        from Bio import Entrez

        self._configure_entrez(config)

        # Search
        handle = Entrez.esearch(db="pubmed", term=query, retmax=limit, retmode="xml")
        search_results = Entrez.read(handle)
        handle.close()

        id_list = search_results.get("IdList", [])
        if not id_list:
            return []

        # Fetch summaries
        handle = Entrez.esummary(db="pubmed", id=",".join(id_list), retmode="xml")
        summaries = Entrez.read(handle)
        handle.close()

        results: list[SearchResult] = []
        for s in summaries:
            authors = s.get("AuthorList", [])
            title = s.get("Title", "")
            pmid = str(s.get("Id", ""))

            results.append(
                SearchResult(
                    title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    snippet=s.get("Title", ""),  # esummary doesn't return abstracts
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=list(authors)[:5],
                    published_date=s.get("PubDate", ""),
                    metadata={
                        "pmid": pmid,
                        "journal": s.get("FullJournalName", ""),
                        "source": s.get("Source", ""),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_python_import("biopython-entrez", "Bio.Entrez")
        if result.ok:
            has_key = bool(config.get("ncbi_api_key"))
            has_email = bool(config.get("ncbi_email"))
            msg = "Biopython Entrez available"
            if has_key:
                msg += " (with API key, 10 req/sec)"
            else:
                msg += " (no API key, 3 req/sec — set 'ncbi_api_key')"
            if not has_email:
                msg += " [WARNING: set 'ncbi_email' per NCBI guidelines]"
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK if has_email else StatusLevel.WARN,
                tier=self.tier,
                active_backend="biopython-entrez",
                message=msg,
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"Biopython not available: {result.error}",
        )

    def _configure_entrez(self, config: Config) -> None:
        from Bio import Entrez
        Entrez.email = config.get("ncbi_email", "social-dive@example.com")
        api_key = config.get("ncbi_api_key")
        if api_key:
            Entrez.api_key = api_key

    @staticmethod
    def _extract_pmid(url: str) -> str | None:
        match = re.search(r"/(\d{5,12})/?", url)
        return match.group(1) if match else None
