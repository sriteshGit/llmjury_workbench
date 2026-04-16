"""Public LLM API via LiteLLM (replaces venice_gentech ChatLLMInvoker + LLMWrapper)."""

from __future__ import annotations

import logging
from typing import Any

import litellm
from litellm import completion

from llmjury.runtime.connector import Connector
from llmjury.support.prompt_constants import CONTENT, HUMAN, SYSTEM, TYPE

logger = logging.getLogger(__name__)


class LLMWrapper:
    """Thin wrapper carrying LiteLLM model id and optional API kwargs (json mode, etc.)."""

    def __init__(self, model_id: str, model_kwargs: dict[str, Any] | None = None) -> None:
        self.model_id = model_id
        self.model_kwargs = dict(model_kwargs or {})


def _messages_lc_to_openai(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = m.get('role') or m.get(TYPE) or 'user'
        if role in ('human', 'user'):
            r = 'user'
        elif role in ('system', SYSTEM):
            r = 'system'
        elif role in ('ai', 'assistant'):
            r = 'assistant'
        else:
            r = 'user'
        content = m.get(CONTENT) or m.get('content') or ''
        out.append({'role': r, 'content': str(content)})
    return out


def _batches_from_prompts_connector(prompts: Connector) -> list[list[dict[str, Any]]]:
    raw = prompts.read_json()
    if raw is None:
        return []
    if isinstance(raw, str):
        return [[{TYPE: HUMAN, CONTENT: raw}]]
    if not isinstance(raw, list) or not raw:
        return []
    if all(isinstance(x, list) for x in raw):
        return raw
    if isinstance(raw[0], dict) and raw[0].get(TYPE) in (
        SYSTEM,
        HUMAN,
        'user',
        'system',
        'ai',
        'assistant',
    ):
        return [raw]
    batches: list[list[dict[str, Any]]] = []
    for item in raw:
        if isinstance(item, list):
            batches.append(item)
        elif isinstance(item, dict):
            batches.append([item])
    return batches


def _complete_one(model_id: str, messages: list[dict[str, Any]], model_kwargs: dict[str, Any]) -> str:
    openai_msgs = _messages_lc_to_openai(messages)
    kwargs = dict(model_kwargs)
    response_format = kwargs.pop('response_format', None)
    try:
        resp = completion(
            model=model_id,
            messages=openai_msgs,
            temperature=kwargs.pop('temperature', 0.2),
            **kwargs,
            **({'response_format': response_format} if response_format else {}),
        )
        choice = resp.choices[0]
        msg = getattr(choice, 'message', None)
        if msg is None:
            return ''
        content = getattr(msg, 'content', None)
        return content if isinstance(content, str) else str(content or '')
    except Exception as e:
        logger.error('LiteLLM completion failed for %s: %s', model_id, e, exc_info=True)
        raise


class ChatLLMInvoker:
    """Drop-in shape compatible with prior ChatLLMInvoker(...).run() -> Connector."""

    def __init__(
        self,
        prompts: Connector,
        llm_wrapper: LLMWrapper,
        stream: bool = False,
        name: str | None = None,
    ) -> None:
        self.prompts = prompts
        self.llm_wrapper = llm_wrapper
        self.stream = stream
        self.name = name

    def run(self) -> Connector:
        if self.stream:
            logger.warning('stream=True is ignored; use non-streaming completion.')
        out = Connector('llm_response')
        batches = _batches_from_prompts_connector(self.prompts)
        texts: list[str] = []
        for batch in batches:
            if not batch:
                continue
            texts.append(_complete_one(self.llm_wrapper.model_id, batch, self.llm_wrapper.model_kwargs))
        joined = '\n\n'.join(texts) if len(texts) > 1 else (texts[0] if texts else '')
        out.add_data(joined)
        return out


# Reduce LiteLLM noise in library mode
litellm.suppress_debug_info = True
