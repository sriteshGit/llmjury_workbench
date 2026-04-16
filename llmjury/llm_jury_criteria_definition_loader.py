# LLMJury Workbench


import logging

from langchain_core.prompts import PromptTemplate
from llmjury.runtime.connector import Connector
from llmjury.runtime.operator import Operator
from llmjury.support.paths import PROMPT_CONFIG_SEARCH_PATH
from llmjury.support.prompt_configuration_manager import PromptConfigurationManager


class LLMJURYCriteriaPromptDefinitionLoader(Operator):
    """
    Create definition prompts for the LLMJURYCriteriaPromptDefinitionLoader.

    .
    The definitions are then used to make final prompts for LLM JURY


    Parameters
    ----------
    prompt_id: str
    identifier used to select prompt configs under the prompt_base_path.
    criteria_name : str
    The criteria for which the definition is to be fetched
    prompt_base_path: str
    The base path under `PROMPT_CONFIG_SEARCH_PATH` where the prompt configuration is stored.
    Default is 'accuracy'.
    name : Optional[str], default=None
    An optional additional name or identifier. Defaults to None if not provided.

    Returns
    -------
    prompts: Connector
    The list of prompts that will be used for making LLM calls.
    """

    VERSION = '1.0.0'

    def __init__(
        self,
        prompt_id: str,
        criteria_name: str,
        logger: logging.Logger,
        prompt_base_path: str,
        name: str | None = None,
    ):
        super().__init__(name=name)
        self.prompt_id = prompt_id
        self.criteria_name = criteria_name
        self.logger = logger
        self.prompt_base_path = prompt_base_path

        self.prompt_config_manager = PromptConfigurationManager(
            base_path=self.prompt_base_path,
            prompt_id=self.prompt_id,
            search_path=PROMPT_CONFIG_SEARCH_PATH,
        )

    def setup(self) -> Connector:
        """Create and return the criteria definition prompts connector.

        Returns
        -------
        prompts: Connector
            The definition prompts of evaluation criteria
        """
        self.prompts = Connector('prompts')
        return self.prompts

    def run(self) -> Connector:
        """Create definition prompts for the LLMJURYCriteriaPromptDefinitionLoader.

        Returns
        -------
        prompts: Connector
            The list of prompts that will be used for making LLM calls.
        """
        self.setup()
        prompts = self.get_prompts()
        self.prompts.add_data(prompts)
        self.prompts.finished()
        return self.prompts

    def get_prompts(self) -> str:
        """Create definition prompts for the LLMJURYCriteriaPromptDefinitionLoader.

        Returns
        -------
        a string which has definition for the evaluation criteria.

        """
        self.logger.debug('Number of GPT calls: 1')
        prompt_template = self.prompt_config_manager.get_prompt_template()
        if isinstance(prompt_template, PromptTemplate):
            prompt_template_str = prompt_template.template
        else:
            prompt_template_str = getattr(prompt_template, 'template', str(prompt_template))

        return prompt_template_str
