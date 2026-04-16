"""Resolve model aliases to LiteLLM model ids (no venice_gentech)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from llmjury.chat_invoker import LLMWrapper


@dataclass
class _ModelClass:
    value: str


@dataclass
class ChatModelSpec:
    """User-facing model handle; `get_llm_wrapper` returns a LiteLLM-backed wrapper."""

    model_id: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        self.model_name = self.model_id
        self.model_class = _ModelClass(self.display_name or self.model_id)

    def get_llm_wrapper(self, model_kwargs: dict[str, Any] | None = None) -> LLMWrapper:
        return LLMWrapper(self.model_id, model_kwargs)


# Friendly names (underscore / legacy venice style) -> LiteLLM model strings.
# Users can also pass any LiteLLM-supported id directly, e.g. "gpt-4o", "anthropic/claude-3-5-sonnet-20241022".
_ALIASES: dict[str, str] = {
    'gpt_4o_mini': 'gpt-4o-mini',
    'gpt_4o': 'gpt-4o',
    'gpt_5_mini': 'gpt-4o-mini',  # public mapping until OpenAI ships GPT-5 to LiteLLM
    'gpt_4': 'gpt-4-turbo',
    'gpt_35_turbo': 'gpt-3.5-turbo',
}


def _normalize_key(name: str) -> str:
    s = name.strip().lower()
    s = s.replace('-', '_')
    return s


def get_model(model_name: str) -> ChatModelSpec:
    """
    Return a ChatModelSpec for LiteLLM.

    Environment (typical):
    - OPENAI_API_KEY for OpenAI models
    - ANTHROPIC_API_KEY for Claude
    - AZURE_API_KEY + AZURE_API_BASE + AZURE_API_VERSION for Azure OpenAI (prefix model with azure/)
    See https://docs.litellm.ai/docs/providers
    """
    key = _normalize_key(model_name)
    if key in _ALIASES:
        resolved = _ALIASES[key]
    else:
        resolved = model_name.strip()

    # Heuristic: deployment-style names often contain dots or long hyphenated ids
    if os.environ.get('LLMJURY_FORCE_AZURE', '').lower() in ('1', 'true', 'yes'):
        if not resolved.startswith('azure/'):
            resolved = f'azure/{resolved}'

    return ChatModelSpec(model_id=resolved, display_name=model_name)


def get_available_models() -> list[str]:
    return sorted({*list(_ALIASES.keys()), 'gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'})


def is_azure_model(model_name: str) -> bool:
    n = model_name.lower()
    if n.startswith('azure/'):
        return True
    return bool(re.search(r'gpt|gemini|claude|o1|o3|nova', n))


def get_available_factory_models() -> dict[str, ChatModelSpec]:
    return {k: get_model(k) for k in _ALIASES}
