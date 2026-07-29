from __future__ import annotations

import os
from typing import Any

from providers.base import ModelResponse
from providers.openai_provider import OpenAIProvider


class NvidiaProvider(OpenAIProvider):
    """NVIDIA NIM exposes an OpenAI-compatible Chat Completions surface.

    Model id must match the one listed by GET /v1/models exactly. Qwen3 was
    retired from NIM on 2026-07-27; `openai/gpt-oss-120b` is verified to support
    both tool calling and tool_choice="required". Override via NVIDIA_MODEL or --model.
    """

    def __init__(self) -> None:
        super().__init__(
            api_key_env="NVIDIA_API_KEY",
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            default_model=os.getenv("NVIDIA_MODEL", "openai/gpt-oss-120b"),
        )

    def complete(self, messages, tools=None, **kwargs: Any) -> ModelResponse:
        # Qwen3 thinking variants prepend reasoning to `content`, which adds noise to
        # transcripts. Set NVIDIA_DISABLE_THINKING=1 to turn it off on models that
        # support the flag; instruct variants ignore it.
        if os.getenv("NVIDIA_DISABLE_THINKING") == "1":
            kwargs.setdefault("extra_body", {"chat_template_kwargs": {"thinking": False}})
        return super().complete(messages, tools, **kwargs)
