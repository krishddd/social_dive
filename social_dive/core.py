"""
Social Dive core orchestrator.

This is the main entry point for programmatic use.  It ties together channels,
LLM providers, and formatters into a single cohesive API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from social_dive.channels import Channel, Content, SearchNotSupportedError, SearchResult
from social_dive.config import Config
from social_dive.doctor import DoctorReport, _discover_channels, check_all, get_registered_channels
from social_dive.llm.base import LLMProvider


def _classify_exception(e: Exception) -> str:
    """Map an exception to a structured error code.

    Allowed values: "rate_limited", "unauthenticated", "timeout",
    "not_found", "error". Used so a channel failure degrades to a
    structured ``Content.error_code``/skip-reason instead of an opaque
    traceback reaching the caller.
    """
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 429:
            return "rate_limited"
        if status in (401, 403):
            return "unauthenticated"
        return "error"
    if isinstance(e, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    # Some channels wrap a third-party client (e.g. the `arxiv` package) that
    # raises its own exception type for an HTTP error rather than httpx's —
    # the status code is only visible in the message. This is a best-effort
    # fallback, not a substitute for real header-based detection (that's
    # Phase 2's http_client.py, see plan decision #3).
    message = str(e)
    if "429" in message:
        return "rate_limited"
    if " 401" in message or " 403" in message:
        return "unauthenticated"
    if isinstance(e, ValueError):
        return "not_found"
    return "error"


@dataclass
class SearchResponse:
    """Aggregated multi-channel search results.

    ``skipped`` maps channel name -> reason string for channels that
    contributed no results (not supported / rate limited / errored),
    distinguishing that from a channel that genuinely searched and found
    nothing — the caller can use this to decide whether to reformulate the
    query rather than treat every empty case identically.
    """
    results: list[SearchResult] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "skipped": self.skipped,
        }


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
        Falls back to the web channel if no specific channel matches. A
        channel that raises while reading degrades to a structured
        ``Content`` with ``error_code`` set, rather than propagating —
        matching the "a broken channel must never crash the caller" rule
        already applied to the doctor report. Only the "no channel could
        even attempt this URL" case still raises, since that's a genuine
        usage error rather than a channel failure.
        """
        # Find matching channel
        for channel in self._channels:
            if channel.name != "web" and channel.can_handle(url):
                return self._dispatch_read(channel, url)

        # Fallback to web channel
        for channel in self._channels:
            if channel.name == "web" and channel.can_handle(url):
                return self._dispatch_read(channel, url)

        raise ValueError(f"No channel can handle URL: {url}")

    def _dispatch_read(self, channel: Channel, url: str) -> Content:
        logger.info(f"Reading {url} via {channel.name}")
        try:
            content = channel.read(url, self._config)
        except Exception as e:
            logger.warning(f"Read failed for {channel.name}: {e}")
            content = Content(
                url=url,
                source_channel=channel.name,
                body=f"[{channel.name} read failed: {e}]",
                error_code=_classify_exception(e),
            )
        # Stamped centrally (not per-channel) so every result's timestamp
        # reflects when the dispatcher actually received it, not whenever
        # each channel happened to construct its Content internally.
        content.fetched_at = datetime.utcnow().isoformat()
        return content

    def read_many(self, urls: list[str]) -> list[Content]:
        """Read several URLs, fetching web pages concurrently via the Rust core.

        For a single URL (or when the Rust ``parallel_fetch`` extension isn't
        available) this is just sequential :meth:`read`, so behavior is
        identical to reading each URL on its own. For multiple URLs it uses the
        Rust concurrent fetcher to grab the raw pages in parallel (GIL released)
        and converts each to Markdown — a bulk web-read fast path, distinct from
        the channel-aware single :meth:`read`.
        """
        if len(urls) <= 1:
            return [self.read(u) for u in urls]

        try:
            from social_dive._core import parallel_fetch
        except ImportError:
            logger.debug("Rust _core unavailable; reading URLs sequentially")
            return [self.read(u) for u in urls]

        results = parallel_fetch(urls)
        fetched_at = datetime.utcnow().isoformat()
        contents = [self._content_from_fetch(r) for r in results]
        for c in contents:
            c.fetched_at = fetched_at
        return contents

    @staticmethod
    def _content_from_fetch(result: Any) -> Content:
        """Convert a Rust ``FetchResult`` into a Content (Markdown body)."""
        if not getattr(result, "ok", False) or getattr(result, "status", 0) != 200:
            return Content(
                url=getattr(result, "url", ""),
                source_channel="web",
                body=f"[fetch failed: {getattr(result, 'error', '') or 'HTTP '}"
                f"{getattr(result, 'status', 0)}]",
                error_code="rate_limited" if getattr(result, "status", 0) == 429 else "error",
                backend="parallel-fetch",
            )
        try:
            from social_dive._core import html_to_markdown

            body = html_to_markdown(result.body)
        except Exception:  # noqa: BLE001 — fall back to the raw body
            body = result.body
        title = ""
        for line in body.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return Content(
            title=title,
            body=body,
            url=result.url,
            source_channel="web",
            backend="parallel-fetch",
        )

    def search(
        self,
        query: str,
        channels: list[str] | None = None,
        limit: int = 10,
    ) -> SearchResponse:
        """Search across channels and return aggregated results.

        Parameters
        ----------
        query
            Search query string.
        channels
            List of channel names to search. If None, searches all channels.
        limit
            Max results per channel.

        Returns
        -------
        SearchResponse
            ``results`` from every channel that found something, plus
            ``skipped`` explaining *why* any channel contributed nothing
            (not supported / rate limited / errored) — see ``SearchResponse``.
        """
        all_results: list[SearchResult] = []
        skipped: dict[str, str] = {}

        target_channels = self._channels
        if channels:
            target_channels = [c for c in self._channels if c.name in channels]
            if not target_channels:
                raise ValueError(f"No matching channels for: {channels}")

        fetched_at = datetime.utcnow().isoformat()
        for channel in target_channels:
            try:
                results = channel.search(query, self._config, limit=limit)
                for r in results:
                    r.fetched_at = fetched_at
                all_results.extend(results)
                logger.debug(f"{channel.name}: {len(results)} results")
            except SearchNotSupportedError as e:
                skipped[channel.name] = f"not_supported: {e}"
            except Exception as e:
                logger.warning(f"Search failed for {channel.name}: {e}")
                skipped[channel.name] = f"{_classify_exception(e)}: {e}"

        # Sort by score (citation count, stars, etc.) descending
        all_results.sort(key=lambda r: r.score, reverse=True)

        return SearchResponse(results=all_results, skipped=skipped)

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
                self._llm = NvidiaProvider(
                    api_key=key, default_model=model or "deepseek-ai/deepseek-v4-flash"
                )

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
                self._llm = AnthropicProvider(
                    api_key=key, default_model=model or "claude-sonnet-4-20250514"
                )

            else:
                logger.warning(f"Unknown LLM provider: {provider_name}")
                return None

        except Exception as e:
            logger.error(f"Failed to initialize LLM provider '{provider_name}': {e}")
            return None

        return self._llm
