"""Markdown output formatter."""

from __future__ import annotations

from social_dive.channels import Content, SearchResult


def format_content(content: Content) -> str:
    """Format Content as clean Markdown with metadata header."""
    parts: list[str] = []

    if content.title:
        parts.append(f"# {content.title}\n")

    meta_parts = []
    if content.authors:
        meta_parts.append(f"**Authors:** {', '.join(content.authors)}")
    if content.published_date:
        meta_parts.append(f"**Published:** {content.published_date}")
    if content.source_channel:
        meta_parts.append(f"**Source:** {content.source_channel}")
    if content.url:
        meta_parts.append(f"**URL:** {content.url}")

    if meta_parts:
        parts.append(" · ".join(meta_parts) + "\n")

    if content.abstract:
        parts.append(f"\n> {content.abstract}\n")

    if content.body:
        parts.append(f"\n{content.body}")

    return "\n".join(parts)


def format_search_results(results: list[SearchResult]) -> str:
    """Format search results as a Markdown list."""
    if not results:
        return "*No results found.*"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        parts.append(f"### {i}. {r.title}")
        meta = f"*{r.source_channel}*"
        if r.authors:
            meta += f" · {', '.join(r.authors[:3])}"
        if r.published_date:
            meta += f" · {r.published_date}"
        parts.append(meta)
        if r.snippet:
            parts.append(f"\n{r.snippet}")
        parts.append(f"\n[Link]({r.url})\n")

    return "\n".join(parts)
