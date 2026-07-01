"""LLM-powered content summarization formatter."""

from __future__ import annotations

from social_dive.channels import Content
from social_dive.config import Config
from social_dive.core import SocialDive


def summarize_content(content: Content, prompt: str | None = None, config: Config | None = None) -> str:
    """Summarize content using the configured LLM provider."""
    sd = SocialDive(config=config)
    return sd.summarize(content, prompt=prompt)
