"""
Abstract LLM provider interface for Social Dive.

All LLM providers (NVIDIA NIM, OpenAI, Anthropic) implement this interface so
the rest of the codebase never touches provider-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompletionResult:
    """Result from an LLM completion call."""
    content: str
    model: str = ""
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)  # prompt_tokens, completion_tokens, total
    raw: Any = None  # original SDK response for advanced use

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "reasoning": self.reasoning,
            "usage": self.usage,
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Subclasses must implement ``complete()`` and ``available_models()``.
    The ``complete()`` method accepts the standard chat-message list format
    (list of ``{"role": ..., "content": ...}`` dicts).
    """

    name: str

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> CompletionResult:
        """Send a chat completion request and return the result."""
        ...

    @abstractmethod
    def available_models(self) -> list[str]:
        """Return a list of model identifiers this provider supports."""
        ...

    def check(self) -> bool:
        """Quick health check — can we reach the API?"""
        try:
            self.complete(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"<LLMProvider:{self.name}>"
