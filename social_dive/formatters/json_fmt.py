"""JSON output formatter."""

from __future__ import annotations

import json

from social_dive.channels import Content, SearchResult


def format_content(content: Content) -> str:
    """Format Content as a JSON string."""
    return json.dumps(content.to_dict(), indent=2, ensure_ascii=False)


def format_search_results(results: list[SearchResult]) -> str:
    """Format search results as a JSON array."""
    return json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)
