"""
NVIDIA NIM LLM provider for Social Dive.

Uses the OpenAI Python SDK pointed at ``integrate.api.nvidia.com/v1``.
Supports all models hosted on NVIDIA NIM: GLM-5.x, MiniMax-M3, DeepSeek-V4,
Mistral Medium 3.5, and any other model the user configures.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from social_dive.llm.base import CompletionResult, LLMProvider


# Default models available on NVIDIA NIM (non-exhaustive)
NVIDIA_MODELS = [
    "deepseek-ai/deepseek-v4-flash",
    "mistralai/mistral-medium-3.5-128b",
    "zhipu-ai/glm-5.2",
    "zhipu-ai/glm-5.1",
    "minimax/minimax-m3",
    "minimax/minimax-m2.7",
    "meta/llama-3.3-70b-instruct",
    "nvidia/nemotron-3-super-120b-a12b",
]

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(LLMProvider):
    """NVIDIA NIM provider — OpenAI-compatible API hosted by NVIDIA.

    Parameters
    ----------
    api_key
        NVIDIA API key (``nvapi-...`` prefix).
    default_model
        Model to use when none is specified in ``complete()`` calls.
    base_url
        Override the NIM endpoint (for self-hosted deployments).
    """

    name = "nvidia"

    def __init__(
        self,
        api_key: str,
        default_model: str = "deepseek-ai/deepseek-v4-flash",
        base_url: str = NVIDIA_BASE_URL,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for the NVIDIA provider. "
                "Install it with: pip install openai"
            )

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._default_model = default_model
        self._base_url = base_url

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> CompletionResult:
        """Send a chat completion request to NVIDIA NIM."""
        model = model or self._default_model
        logger.debug(f"NVIDIA completion: model={model}, msgs={len(messages)}")

        # Build extra_body for models that support reasoning
        extra_body: dict[str, Any] = {}
        if "deepseek" in model.lower():
            extra_body["chat_template_kwargs"] = {
                "thinking": True,
                "reasoning_effort": kwargs.pop("reasoning_effort", "high"),
            }
        if "minimax" in model.lower() and kwargs.pop("reasoning_split", False):
            extra_body["reasoning_split"] = True

        # Merge any remaining kwargs into extra_body
        extra_body.update(kwargs.pop("extra_body", {}))

        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=kwargs.pop("top_p", 0.95),
            stream=False,
            **({"extra_body": extra_body} if extra_body else {}),
        )

        choice = completion.choices[0]
        content = choice.message.content or ""

        # Extract reasoning if available (DeepSeek, MiniMax-M3)
        reasoning = (
            getattr(choice.message, "reasoning", None)
            or getattr(choice.message, "reasoning_content", None)
            or ""
        )

        usage = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }

        return CompletionResult(
            content=content,
            model=model,
            reasoning=reasoning,
            usage=usage,
            raw=completion,
        )

    def available_models(self) -> list[str]:
        """Return known NVIDIA NIM models.

        For a live list, query the /v1/models endpoint.
        """
        return list(NVIDIA_MODELS)

    def list_remote_models(self) -> list[str]:
        """Query the NVIDIA NIM /v1/models endpoint for all available models."""
        try:
            models = self._client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.warning(f"Could not list remote models: {e}")
            return self.available_models()
