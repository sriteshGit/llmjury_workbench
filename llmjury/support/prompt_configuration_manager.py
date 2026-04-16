"""Load prompt templates from JSON + text files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)


class PromptConfigurationManager:
    """Resolve prompt_id under base_path relative to search_path."""

    def __init__(self, base_path: str, prompt_id: str, search_path: Path) -> None:
        self.base_path = base_path
        self.prompt_id = prompt_id
        self.search_path = Path(search_path)
        cfg = self.search_path / base_path / 'configs' / f'{prompt_id}.json'
        if not cfg.exists():
            raise FileNotFoundError(f'Prompt config not found: {cfg}')
        self._config = json.loads(cfg.read_text(encoding='utf-8'))
        raw_vars = self._config.get('input_variables') or {}
        self.input_variables: dict[str, Any] = {k: (v if v is not None else '') for k, v in raw_vars.items()}

    def update_input_vars(self, **kwargs: Any) -> None:
        self.input_variables.update(kwargs)

    def get_prompt_template(self) -> PromptTemplate:
        version = self._config['version']
        pid = self._config['id']
        rel = self._config.get('prompt_text_path', 'text/')
        txt_path = self.search_path / self.base_path / rel / version / f'{pid}.txt'
        if not txt_path.exists():
            raise FileNotFoundError(f'Prompt text not found: {txt_path}')
        template_str = txt_path.read_text(encoding='utf-8')
        try:
            return PromptTemplate.from_template(template_str)
        except ValueError:
            logger.warning('Falling back to raw PromptTemplate for %s', self.prompt_id)
            return PromptTemplate(template=template_str, input_variables=list(self.input_variables.keys()))
