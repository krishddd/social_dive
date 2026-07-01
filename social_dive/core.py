"""
Social Dive core orchestrator.

This is the main entry point for programmatic use.  It ties together channels,
LLM providers, and formatters into a single cohesive API.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from social_dive.channels import Channel, Content, SearchResult
from social_dive.config import Config
from social_dive.doctor import DoctorReport, check_all, get_registered_channels, _discover_channels
from social_dive.llm.base import LLMProvider


class SocialDive:
    """Main orchestrator for Social Dive.

    Usage::

        sd = SocialDive()
        content = sd.read("https://arxiv.org/abs/2401.12345")
        results = sd.search("transformer architecture", channels=["arxiv", "semantic_scholar"])
        summary = sd.summarize(content)
    """

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()
        self._llm: LLMProvider | None = None
        self._channels: list[Channel] = []
        self._init_channels()

    def read(self, url: str) -> Content:
        """Read content from any supported URL.

        Dispatches to the first channel whose ``can_handle()`` returns True.
        Falls back to the web channel if no specific channel matches.
        """
        # Find matching channel
        for channel in self._channels:
            if channel.name != "web" and channel.can_handle(url):
                logger.info(f"Reading {url} via {channel.name}")
                return channel.read(url, self._config)

        # Fallback to web channel
        for channel in self._channels:
            if channel.name == "web" and channel.can_handle(url):
                logger.info(f"Reading {url} via web (fallback)")
                return channel.read(url, self._config)

        raise ValueError(f"No channel can handle URL: {url}")

    def search(
        self,
        query: str,
        channels: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Search across channels and return aggregated results.

        Parameters
        ----------
        query
            Search query string.
        channels
            List of channel names to search. If None, searches all channels.
        limit
            Max results per channel.
        """
        all_results: list[SearchResult] = []

        target_channels = self._channels
        if channels:
            target_channels = [c for c in self._channels if c.name in channels]
            if not target_channels:
                raise ValueError(f"No matching channels for: {channels}")

        for channel in target_channels:
            try:
                results = channel.search(query, self._config, limit=limit)
                all_results.extend(results)
                logger.debug(f"{channel.name}: {len(results)} results")
            except Exception as e:
                logger.warning(f"Search failed for {channel.name}: {e}")

        # Sort by score (citation count, stars, etc.) descending
        all_results.sort(key=lambda r: r.score, reverse=True)

        return all_results

    def doctor(self) -> DoctorReport:
        """Run health checks on all channels."""
        return check_all(self._config)

    def summarize(self, content: Content, prompt: str | None = None) -> str:
        """Summarize content using the configured LLM provider."""
        provider = self._get_llm()
        if not provider:
            return "[LLM not configured — set nvidia_api_key, openai_api_key, or anthropic_api_key]"

        system_prompt = (
            "You are a research assistant. Summarize the following content concisely, "
            "highlighting key findings, methods, and conclusions."
        )

        user_content = f"Title: {content.title}\n\n"
        if content.abstract:
            user_content += f"Abstract: {content.abstract}\n\n"
        user_content += f"Content:\n{content.body[:8000]}"  # Cap to avoid token limits

        if prompt:
            user_content += f"\n\nAdditional instructions: {prompt}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            result = provider.complete(messages)
            return result.content
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            return f"[Summarization failed: {e}]"

    def get_channel(self, name: str) -> Channel | None:
        """Get a specific channel by name."""
        for c in self._channels:
            if c.name == name:
                return c
        return None

    def list_channels(self) -> list[str]:
        """Return names of all registered channels."""
        return [c.name for c in self._channels]

    # -- internal ---

    def _init_channels(self) -> None:
        """Discover and instantiate all registered channels."""
        _discover_channels()
        for cls in get_registered_channels():
            try:
                self._channels.append(cls())
            except Exception as e:
                logger.warning(f"Could not instantiate channel {cls}: {e}")

    def _get_llm(self) -> LLMProvider | None:
        """Lazy-init the LLM provider based on config."""
        if self._llm is not None:
            return self._llm

        provider_name = self._config.get("llm_provider", "nvidia")
        model = self._config.get("llm_model")

        try:
            if provider_name == "nvidia":
                key = self._config.get("nvidia_api_key")
                if not key:
                    return None
                from social_dive.llm.nvidia import NvidiaProvider
                self._llm = NvidiaProvider(api_key=key, default_model=model or "deepseek-ai/deepseek-v4-flash")

            elif provider_name == "openai":
                key = self._config.get("openai_api_key")
                if not key:
                    return None
                from social_dive.llm.openai_provider import OpenAIProvider
                self._llm = OpenAIProvider(api_key=key, default_model=model or "gpt-4o")

            elif provider_name == "anthropic":
                key = self._config.get("anthropic_api_key")
                if not key:
                    return None
                from social_dive.llm.anthropic_provider import AnthropicProvider
                self._llm = AnthropicProvider(api_key=key, default_model=model or "claude-sonnet-4-20250514")

            else:
                logger.warning(f"Unknown LLM provider: {provider_name}")
                return None

        except Exception as e:
            logger.error(f"Failed to initialize LLM provider '{provider_name}': {e}")
            return None

        return self._llm
