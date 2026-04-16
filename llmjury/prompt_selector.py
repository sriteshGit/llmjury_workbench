#   ADOBE CONFIDENTIAL
#   ___________________
#
#   Copyright 2024 Adobe
#   All Rights Reserved.
#
#   NOTICE:  All information contained herein is, and remains
#   the property of Adobe and its suppliers, if any.  The
#   intellectual and technical concepts contained herein are
#   proprietary to Adobe and its suppliers and are protected
#   by all applicable intellectual property laws, including
#   trade secret and copyright laws.  Dissemination of this
#   information or reproduction of this material is strictly
#   forbidden unless prior written permission is obtained
#   from Adobe.

from llmjury.constants import (
    DEFAULT_CONSOLIDATION_VERSION,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_METRICS_VERSION,
    EvaluationMode,
    PromptFamily,
)
from llmjury.prompt_version_config import PromptVersionConfig


class PromptConfig:
    """Dataclass to hold prompt configuration IDs."""

    def __init__(
        self,
        jury_prompt_id: str,
        criteria_definition_id_template: str,
        consolidation_prompt_id: str,
        custom_prompt_template: str | None = None,
    ):
        self.jury_prompt_id = jury_prompt_id
        self.criteria_definition_id_template = criteria_definition_id_template
        self.consolidation_prompt_id = consolidation_prompt_id
        self.custom_prompt_template = custom_prompt_template


class PromptSelector:
    """Class to select prompt configurations based on content type from prompt_versions.json."""

    @classmethod
    def get_config(
        cls,
        content_type: str | None,
        custom_prompt_template: str | None = None,
        evaluation_mode: EvaluationMode = EvaluationMode.METRICS,
    ) -> PromptConfig:
        """Get prompt configuration for a given content type from prompt_versions.json."""
        if custom_prompt_template:
            return PromptConfig(
                jury_prompt_id=PromptFamily.CUSTOM.value,
                criteria_definition_id_template=PromptFamily.CUSTOM.value,
                consolidation_prompt_id=f'{PromptFamily.CONSOLIDATION.value}_{DEFAULT_CONSOLIDATION_VERSION}',
                custom_prompt_template=custom_prompt_template,
            )

        if evaluation_mode == EvaluationMode.QUESTION_ANSWER:
            return PromptConfig(
                jury_prompt_id=PromptFamily.QNA_WITH_SOURCE.value,  # Will be determined dynamically
                criteria_definition_id_template='',  # Not used in this mode
                consolidation_prompt_id=f'{PromptFamily.CONSOLIDATION.value}_{DEFAULT_CONSOLIDATION_VERSION}',
            )
        if evaluation_mode == EvaluationMode.COMPARISON:
            return PromptConfig(
                jury_prompt_id=PromptFamily.COMPARISON_WITH_SOURCE.value,  # Will be determined dynamically
                criteria_definition_id_template='',
                consolidation_prompt_id=f'{PromptFamily.CONSOLIDATION.value}_{DEFAULT_CONSOLIDATION_VERSION}',
            )

        # Get configuration from prompt_versions.json
        if not content_type:
            content_type = DEFAULT_CONTENT_TYPE

        try:
            # Get the version for llm_jury criteria from the content type
            version = PromptVersionConfig.get_prompt_version(
                PromptFamily.LLM_JURY.value, content_type=content_type, evaluation_mode=EvaluationMode.METRICS.value
            )

            return PromptConfig(
                jury_prompt_id=f'{PromptFamily.LLM_JURY.value}_{version}',
                criteria_definition_id_template=f'{{criteria}}_definition_{version}',
                consolidation_prompt_id=f'{PromptFamily.CONSOLIDATION.value}_{DEFAULT_CONSOLIDATION_VERSION}',
            )
        except Exception:
            # Fallback to default if there's any error
            return PromptConfig(
                jury_prompt_id=f'{PromptFamily.LLM_JURY.value}_{DEFAULT_METRICS_VERSION}',
                criteria_definition_id_template=f'{{criteria}}_definition_{DEFAULT_METRICS_VERSION}',
                consolidation_prompt_id=f'{PromptFamily.CONSOLIDATION.value}_{DEFAULT_CONSOLIDATION_VERSION}',
            )

    @classmethod
    def get_comparison_prompt_id(cls, has_source: bool) -> str:
        """Return the correct comparison prompt id based on source availability."""
        return PromptFamily.COMPARISON_WITH_SOURCE.value if has_source else PromptFamily.COMPARISON_WITHOUT_SOURCE.value

    @classmethod
    def get_question_answer_prompt_id(cls, has_source: bool) -> str:
        """Return the correct Q&A prompt id based on source availability."""
        return PromptFamily.QNA_WITH_SOURCE.value if has_source else PromptFamily.QNA_WITHOUT_SOURCE.value
