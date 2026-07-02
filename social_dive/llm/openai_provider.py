"""
OpenAI LLM provider for Social Dive.

Uses the standard OpenAI Python SDK pointed at ``api.openai.com/v1``.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from social_dive.llm.base import CompletionResult, LLMProvider

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o3",
    "o3-mini",
    "gpt-4-turbo",
]


class OpenAIProvider(LLMProvider):
    """OpenAI native provider."""

    name = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-4o") -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai: pip install openai")

        self._client = OpenAI(api_key=api_key)
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
        logger.debug(f"OpenAI completion: model={model}, msgs={len(messages)}")

        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        # stream=False above should select the non-streaming overload, but the
        # SDK's overload resolution doesn't always narrow it — assert defends
        # against a Stream slipping through at runtime too, not just the type
        # checker.
        from openai import Stream
        assert not isinstance(completion, Stream)

        choice = completion.choices[0]
        usage = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }

        return CompletionResult(
            content=choice.message.content or "",
            model=model,
            usage=usage,
            raw=completion,
        )

    def available_models(self) -> list[str]:
        return list(OPENAI_MODELS)
