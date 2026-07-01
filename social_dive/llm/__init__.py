"""LLM backend abstraction layer for Social Dive."""

from social_dive.llm.base import CompletionResult, LLMProvider
from social_dive.llm.nvidia import NvidiaProvider

__all__ = ["CompletionResult", "LLMProvider", "NvidiaProvider"]
