"""Prompt bundle location shipped inside the llmjury package."""

from pathlib import Path

_LLMJURY_PKG = Path(__file__).resolve().parent.parent
PROMPT_CONFIG_SEARCH_PATH = _LLMJURY_PKG / 'data' / 'prompts'
