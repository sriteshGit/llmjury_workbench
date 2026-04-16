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

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from venice.core.Connector import Connector
from venice.core.Operator import Operator
from venice_gentech.utils.prompt_configuration_manager import PromptConfigurationManager

from llmjury.constants import PromptFamily
from llmjury.support.prompt_constants import CONTENT, HUMAN, SYSTEM, TYPE
from llmjury.support.paths import PROMPT_CONFIG_SEARCH_PATH


class LLMJURYPromptLoader(Operator):
    """
    Create prompts for the LLMJURYPromptLoader.

    The prompts are created by inserting Summary, and context(i.e. section text) in the instruction template.
    The prompts are then used to make language model calls.
    The operator returns the list of prompts and the dictionary containing the inputs needed by those prompts.
    The prompt at nth index in the prompts list will have 'n' as key in the prompt input dictionary.

    Parameters
    ----------
    prompt_id: str
        identifier used to select prompt configs under the prompt_base_path.
    summary : str
        The summary to be used.
    section_text : str
        The section_text associated with the summary
    prompt_base_path: str
        The base path under `PROMPT_CONFIG_SEARCH_PATH` where the prompt configuration is stored.
        Default is 'llmJURY/metrics'.
    name : Optional[str], default=None
        An optional additional name or identifier. Defaults to None if not provided.
    custom_prompt_template: str | None, default=None
        An optional custom prompt template to use instead of the default one.
    question: str | None, default=None
        An optional question to be used in the prompt.
    summary2: str | None, default=None
        An optional summary to be used in the prompt.
    additional_info: str | None, default=None
        An optional additional details or information about the analysis to include in the prompt.

    Returns
    -------
    prompts: Connector
        The list of prompts that will be used for making LLM calls.
    """

    VERSION = '0.2.0'

    USER_MESSAGE = """
    "Source Text": {section_text}
    "Summary": {summary}
    """
    USER_MESSAGE_FOR_MINDMAP = """
    "Source Text": {section_text}
    "Mindmap": {summary}
    """
    USER_MESSAGE_WITH_QUESTION = """
    "Question": {question}
    "Source Text": {section_text}
    "Answer": {summary}
    """
    USER_MESSAGE_FOR_COMPARISON = """
    "Source Text": {section_text}
    "Response 1": {summary1}
    "Response 2": {summary2}
    """
    USER_MESSAGE_FOR_COMPARISON_NO_SOURCE = """
    "Response 1": {summary1}
    "Response 2": {summary2}
    """
    USER_MESSAGE_FOR_GROUND_TRUTH_COMPARISON = """
    "Reference Text": {section_text}
    "Answer Text": {summary}
    """
    USER_MESSAGE_FOR_QNA_WITHOUT_SOURCE = """
    "Question": {section_text}
    "Answer": {summary}
    """

    def __init__(
        self,
        prompt_id: str,
        section_text: str,
        summary: str,
        criteria_name: str,
        criteria_definition: str,
        logger: logging.Logger,
        prompt_base_path: str = 'llmJURY/metrics',
        name: str | None = None,
        custom_prompt_template: str | None = None,
        question: str | None = None,
        summary2: str | None = None,
        content_type: str | None = None,
        additional_info: str | None = None,
    ):
        super().__init__(name=name)
        self.prompt_id = prompt_id
        self.section_text = section_text
        self.summary = summary
        self.criteria_name = criteria_name
        self.criteria_definition = criteria_definition
        self.logger = logger
        self.prompt_base_path = prompt_base_path
        self.custom_prompt_template = custom_prompt_template
        self.question = question
        self.summary2 = summary2
        self.content_type = content_type
        self.additional_info = additional_info

        if not self.custom_prompt_template:
            self.prompt_config_manager = PromptConfigurationManager(
                base_path=self.prompt_base_path,
                prompt_id=self.prompt_id,
                search_path=PROMPT_CONFIG_SEARCH_PATH,
            )

    def setup(self) -> Connector:
        """Create and return the llm jury prompts connector.

        Returns
        -------
        prompts: Connector
            The list of prompts that will be used for making LLM calls.
        """
        self.prompts = Connector('prompts')
        return self.prompts

    def run(self) -> Connector:
        """Generate prompts for the LLMJURYPromptLoader.

        Returns
        -------
        prompts: Connector
            The list of prompts that will be used for making LLM calls.
        """
        prompts = self.get_prompts()
        self.prompts.add_data(prompts)
        self.prompts.finished()
        return self.prompts

    def get_prompts(self) -> list[list[dict[str, str]]]:
        """Create prompts by populating the instruction template with summary, section_text etc.

        Returns
        -------
        list[list[dict[str, str]]]:
            List of prompt texts for making language model calls.
            Dictionary containing the input fields used for creating prompts and other metadata. The fields are
                - summary
                - section_text

        """
        prompts_list = []
        self.logger.debug('Number of GPT calls: 1')
        if self.custom_prompt_template:
            custom_prompt_template = PromptTemplate.from_template(self.custom_prompt_template)
            # Provide all available variables for flexibility in custom prompts
            input_variables = {
                'criteria_name': self.criteria_name,
                'criteria_definition': self.criteria_definition,
                'source': self.section_text,
                'response': self.summary,
                'question': self.question or '',
                'response2': self.summary2 or '',
                'additional_data': self.additional_info or '',
            }
            filled_system_prompt = custom_prompt_template.format(**input_variables)
        else:
            prompt_template: PromptTemplate | FewShotPromptTemplate = self.prompt_config_manager.get_prompt_template()
            if isinstance(prompt_template, PromptTemplate):
                # Update available variables, but only substitute declared variables to avoid KeyError
                self.prompt_config_manager.update_input_vars(
                    criteria_name=self.criteria_name,
                    criteria_definition=self.criteria_definition,
                )
                try:
                    declared_vars = getattr(prompt_template, 'input_variables', [])
                    safe_values = {
                        var: self.prompt_config_manager.input_variables.get(var, '') for var in declared_vars
                    }
                    filled_system_prompt = prompt_template.format(**safe_values)
                except Exception:
                    # Fallback to raw template to prevent failures from literal JSON braces
                    filled_system_prompt = prompt_template.template
            else:
                return []

        # Use routing method for extensibility
        user_message = self._get_user_message()

        complete_prompt = [
            {TYPE: SYSTEM, CONTENT: filled_system_prompt},
            {
                TYPE: HUMAN,
                CONTENT: user_message,
            },
        ]

        prompts_list.append(complete_prompt)

        return prompts_list

    def _get_user_message(self) -> str:
        """Determine the appropriate user message template based on prompt configuration.

        Uses a priority-based routing system where conditions are checked in order
        and the first match is returned. Easy to extend by adding new rules.

        Returns
        -------
        str
            The formatted user message
        """
        # Routing rules: (condition, template, format_kwargs)
        # Rules are checked in order, first match wins
        routing_rules: list[tuple[Callable[[], bool], str, Callable[[], dict[str, Any]]]] = [
            # 1. Prompt ID-based routing (highest priority)
            (
                lambda: PromptFamily.COMPARISON_WITH_GROUND_TRUTH.value in self.prompt_id,
                self.USER_MESSAGE_FOR_GROUND_TRUTH_COMPARISON,
                lambda: {'section_text': self.section_text, 'summary': self.summary},
            ),
            (
                lambda: PromptFamily.QNA_WITHOUT_SOURCE.value in self.prompt_id,
                self.USER_MESSAGE_FOR_QNA_WITHOUT_SOURCE,
                lambda: {'section_text': self.section_text, 'summary': self.summary},
            ),
            # 2. Content-type based routing
            (
                lambda: self.content_type == 'mindmap',
                self.USER_MESSAGE_FOR_MINDMAP,
                lambda: {'section_text': self.section_text, 'summary': self.summary},
            ),
            # 3. Data-driven routing (by presence of fields)
            (
                lambda: bool(self.summary2 and self.section_text),
                self.USER_MESSAGE_FOR_COMPARISON,
                lambda: {'section_text': self.section_text, 'summary1': self.summary, 'summary2': self.summary2},
            ),
            (
                lambda: bool(self.summary2 and not self.section_text),
                self.USER_MESSAGE_FOR_COMPARISON_NO_SOURCE,
                lambda: {'summary1': self.summary, 'summary2': self.summary2},
            ),
            (
                lambda: bool(self.question),
                self.USER_MESSAGE_WITH_QUESTION,
                lambda: {'question': self.question, 'section_text': self.section_text, 'summary': self.summary},
            ),
            # 4. Default fallback (always matches)
            (lambda: True, self.USER_MESSAGE, lambda: {'section_text': self.section_text, 'summary': self.summary}),
        ]

        # Execute routing: check each rule in order
        user_message = ''
        for condition, template, kwargs_fn in routing_rules:
            if condition():
                user_message = template.format(**kwargs_fn())
                break

        # If no match found (should never happen due to default rule), use fallback
        if not user_message:
            user_message = self.USER_MESSAGE.format(section_text=self.section_text, summary=self.summary)

        # Append additional info if present
        if self.additional_info:
            user_message += f'\n    "Additional Details": {self.additional_info}'

        return user_message
