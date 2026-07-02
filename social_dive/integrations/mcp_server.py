"""
MCP (Model Context Protocol) server for Social Dive.

Exposes Social Dive capabilities as MCP tools that AI agents can discover
and invoke via the FastMCP server interface.

Usage:
    python -m social_dive.integrations.mcp_server
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from social_dive.core import SocialDive

# Initialize MCP server
mcp = FastMCP("SocialDive")

# Shared instance (lazy-init)
_sd: SocialDive | None = None


def _get_sd() -> SocialDive:
    global _sd
    if _sd is None:
        _sd = SocialDive()
    return _sd


@mcp.tool()
def read_url(url: str) -> str:
    """Read and extract content from any supported URL.

    Supports 16+ sources: arXiv, GitHub, YouTube, Wikipedia, PubMed,
    Semantic Scholar, Hacker News, Stack Overflow, DEV.to, RSS feeds,
    Crossref DOIs, OpenAlex, Europe PMC, and any web page.

    Returns structured content in Markdown format with metadata.
    """
    sd = _get_sd()
    content = sd.read(url)

    from social_dive.formatters.markdown import format_content
    return format_content(content)


@mcp.tool()
def search_sources(query: str, channels: str = "all", limit: int = 10) -> str:
    """Search across academic, code, and web knowledge sources.

    Args:
        query: The search query string.
        channels: Comma-separated channel names (e.g. "arxiv,github,semantic_scholar")
                  or "all" to search everything.
        limit: Maximum results per channel (default 10).

    Returns:
        JSON object with a "results" array (title, URL, snippet, metadata)
        and a "skipped" map of channel name -> reason for any channel that
        contributed nothing (not supported / rate limited / errored) — use
        this to decide whether reformulating the query is worth trying.
    """
    sd = _get_sd()
    channel_list = None if channels == "all" else channels.split(",")
    response = sd.search(query, channels=channel_list, limit=limit)
    return json.dumps(response.to_dict(), indent=2, ensure_ascii=False)


@mcp.tool()
def check_health() -> str:
    """Report which Social Dive channels are available and working.

    Returns a JSON report showing the status of each channel,
    including which backend is active and any issues detected.
    """
    sd = _get_sd()
    report = sd.doctor()
    return json.dumps(report.to_dict(), indent=2)


@mcp.tool()
def summarize_url(url: str, prompt: str = "") -> str:
    """Read content from a URL and summarize it using the configured LLM.

    Args:
        url: The URL to read and summarize.
        prompt: Optional custom instructions for the summarization.

    Returns:
        An LLM-generated summary of the content.
    """
    sd = _get_sd()
    content = sd.read(url)
    summary = sd.summarize(content, prompt=prompt or None)
    return f"# Summary: {content.title}\n\n{summary}"


@mcp.tool()
def list_channels() -> str:
    """List all available Social Dive channels and their status.

    Returns a JSON object mapping channel names to their tier
    (zero-config, needs-key, needs-tool).
    """
    sd = _get_sd()
    channels = []
    for ch in sd._channels:
        channels.append({
            "name": ch.name,
            "tier": ch.tier.value,
            "backends": ch.backends,
        })
    return json.dumps(channels, indent=2)


if __name__ == "__main__":
    mcp.run()
