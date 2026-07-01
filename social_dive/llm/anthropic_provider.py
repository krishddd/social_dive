"""
Anthropic LLM provider for Social Dive.

Uses the ``anthropic`` SDK for Claude models.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from social_dive.llm.base import CompletionResult, LLMProvider


ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-haiku-20241022",
]


class AnthropicProvider(LLMProvider):
    """Anthropic provider for Claude models."""

    name = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-20250514") -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Install anthropic: pip install anthropic "
                "(or pip install social-dive[anthropic])"
            )

        self._client = anthropic.Anthropic(api_key=api_key)
        self._default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> CompletionResult:
        model = model or self._default_model
        logger.debug(f"Anthropic completion: model={model}, msgs={len(messages)}")

        # Anthropic requires system message to be separate
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_msg = m.get("content", "")
            else:
                chat_messages.append(m)

        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_msg if system_msg else "You are a helpful assistant.",
            messages=chat_messages,  # type: ignore[arg-type]
            temperature=temperature,
        )

        content = ""
        for block in msg.content:
            if hasattr(block, "text"):
                content += block.text

        usage = {}
        if msg.usage:
            usage = {
                "prompt_tokens": msg.usage.input_tokens,
                "completion_tokens": msg.usage.output_tokens,
                "total_tokens": msg.usage.input_tokens + msg.usage.output_tokens,
            }

        return CompletionResult(
            content=content,
            model=model,
            usage=usage,
            raw=msg,
        )

    def available_models(self) -> list[str]:
        return list(ANTHROPIC_MODELS)
