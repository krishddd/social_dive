"""
MCP (Model Context Protocol) server for Social Dive.

Exposes Social Dive capabilities as MCP tools that AI agents (Claude Code,
Cursor, …) can discover and invoke. Tool names follow the official
reference-server convention (snake_case ``verb_noun``), and every tool is
annotated ``readOnlyHint`` / ``openWorldHint`` so MCP hosts can auto-approve
and parallelize them.

The actual work lives in plain ``_do_*`` helpers (import-light, unit-testable
without the MCP runtime); the ``@mcp.tool`` functions are thin wrappers.

Usage:
    python -m social_dive.integrations.mcp_server
"""

from __future__ import annotations

import inspect
import json

from loguru import logger
from mcp.server.fastmcp import FastMCP

from social_dive.core import SocialDive

mcp = FastMCP("SocialDive")

# Shared instance (lazy-init)
_sd: SocialDive | None = None


def _get_sd() -> SocialDive:
    global _sd
    if _sd is None:
        _sd = SocialDive()
    return _sd


def _readonly_kwargs() -> dict:
    """Best-effort read-only/open-world annotations, tolerant of MCP versions.

    ``ToolAnnotations`` and the ``annotations`` kwarg landed after the pinned
    floor (mcp>=1.0), so probe for support and degrade to no annotations rather
    than failing to import on an older runtime.
    """
    try:
        from mcp.types import ToolAnnotations

        if "annotations" in inspect.signature(mcp.tool).parameters:
            return {
                "annotations": ToolAnnotations(readOnlyHint=True, openWorldHint=True)
            }
    except Exception:  # noqa: BLE001 — annotations are optional metadata
        pass
    return {}


_RO = _readonly_kwargs()


# ---------------------------------------------------------------------------
# Logic (no MCP dependency — unit-testable)
# ---------------------------------------------------------------------------

def _do_read(url: str) -> str:
    from social_dive.formatters.markdown import format_content

    content = _get_sd().read(url)
    return format_content(content)


def _do_read_many(urls: list[str]) -> str:
    contents = _get_sd().read_many(urls)
    return json.dumps([c.to_dict() for c in contents], indent=2, ensure_ascii=False)


def _do_search(query: str, channels: str = "all", limit: int = 10) -> str:
    channel_list = None if channels == "all" else channels.split(",")
    response = _get_sd().search(query, channels=channel_list, limit=limit)
    return json.dumps(response.to_dict(), indent=2, ensure_ascii=False)


def _do_check_health() -> str:
    return json.dumps(_get_sd().doctor().to_dict(), indent=2, ensure_ascii=False)


def _do_summarize(url: str, prompt: str = "") -> str:
    sd = _get_sd()
    content = sd.read(url)
    summary = sd.summarize(content, prompt=prompt or None)
    return f"# Summary: {content.title}\n\n{summary}"


def _do_list_channels() -> str:
    channels = [
        {"name": ch.name, "tier": ch.tier.value, "backends": ch.backends}
        for ch in _get_sd()._channels
    ]
    return json.dumps(channels, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool(**_RO)
def read_url(url: str) -> str:
    """Read and extract content from any supported URL.

    Supports 15+ sources: arXiv, GitHub, YouTube, Wikipedia, PubMed,
    Semantic Scholar, Hacker News, Stack Overflow, DEV.to, RSS feeds,
    Crossref DOIs, OpenAlex, Europe PMC, and any web page. Returns structured
    Markdown with metadata; the source URL is verbatim, safe to cite.
    """
    return _do_read(url)


@mcp.tool(**_RO)
def read_many(urls: list[str]) -> str:
    """Read multiple URLs concurrently and return a JSON array of results.

    Faster than reading each URL separately (fetched in parallel). Each entry
    carries its url, title, backend, and — on failure — a structured
    error_code rather than aborting the whole batch.
    """
    return _do_read_many(urls)


@mcp.tool(**_RO)
def search(query: str, channels: str = "all", limit: int = 10) -> str:
    """Search across academic, code, and web knowledge sources.

    Args:
        query: The search query string.
        channels: Comma-separated channel names (e.g. "arxiv,github") or "all".
        limit: Maximum results per channel (default 10).

    Returns a JSON object with "results" (each with a verbatim URL) and
    "skipped" — a map of channel -> why it returned nothing (not_supported,
    rate_limited, …), so you can tell "found nothing" from "couldn't search".
    """
    return _do_search(query, channels, limit)


@mcp.tool(name="search_sources", **_RO)
def search_sources(query: str, channels: str = "all", limit: int = 10) -> str:
    """DEPRECATED alias for `search` — kept one release for compatibility.

    Use the `search` tool instead; this forwards to it.
    """
    logger.warning("MCP tool 'search_sources' is deprecated; use 'search' instead")
    return _do_search(query, channels, limit)


@mcp.tool(**_RO)
def check_health() -> str:
    """Report which Social Dive channels are available and working.

    Returns a JSON report of each channel's status, active backend, and any
    issues — run this first to see which channels to use.
    """
    return _do_check_health()


@mcp.tool(**_RO)
def summarize_url(url: str, prompt: str = "") -> str:
    """Read content from a URL and summarize it using the configured LLM.

    Args:
        url: The URL to read and summarize.
        prompt: Optional custom instructions for the summarization.
    """
    return _do_summarize(url, prompt)


@mcp.tool(**_RO)
def list_channels() -> str:
    """List all available Social Dive channels with their tier and backends."""
    return _do_list_channels()


if __name__ == "__main__":
    mcp.run()
