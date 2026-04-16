# LLMJury Workbench


import logging
import os
from typing import Any

from llmjury.constants import EvaluationMode
from llmjury.model_factory import ChatModelSpec
from llmjury.runtime.connector import Connector
from llmjury.runtime.operator import Operator
from llmjury.llm_jury_per_section import LLMJURYPerSection
from llmjury.prompt_version_config import PromptVersionConfig


class LLMJuryEvaluator(Operator):
    """
    Multi-mode LLM-based evaluator supporting metrics, question-answer, and comparison evaluation modes.

    This evaluator can handle different content types (summary, overview, podcast, daa_agents_response)
    and evaluation modes (metrics, question_answer, comparison) based on the data structure and configuration.

    Parameters
    ----------
    eval_data : Connector
       Connector that contains all the eval format json files. coords: section_id
    criteria_to_be_evaluated : list[str]
       List of criteria to evaluate (for metrics mode)
    model_list : list[ChatModelSpec]
       List of LLM models to use for evaluation
    name : str | None
       Optional name for the operator
    calc_avg_and_std : bool, default=True
       Whether to calculate average and standard deviation
    logger : logging.Logger | None
       Logger to use for logging
    prompt_config_path : str | None
       Path to prompt version config file
    result_type : str | None
       Optional result type for evaluation
    custom_prompt_template : str | None
       Optional custom prompt template
    evaluation_mode : EvaluationMode
       The evaluation mode to use (metrics, question_answer, comparison)
    parallelism : int | None, default=None
       Number of sections to evaluate concurrently. If None, uses a sensible default based on CPU count
       (typically 2-3x CPU count for I/O-bound LLM API calls). Explicitly set to 1 for sequential
       evaluation or higher for more parallelism. Defaults to None (auto-detect).
    """

    VERSION = '3.0.0'

    def __init__(
        self,
        eval_data: Connector,
        criteria_to_be_evaluated: list[str],
        model_list: list[ChatModelSpec],
        name: str | None = None,
        calc_avg_and_std: bool = True,
        logger: logging.Logger | None = None,
        prompt_config_path: str | None = None,
        result_type: str | None = None,
        custom_prompt_template: str | None = None,
        evaluation_mode: EvaluationMode = EvaluationMode.METRICS,
        parallelism: int | None = None,
    ):
        if parallelism is None:
            cpu_count = os.cpu_count() or 4
            parallelism = min(cpu_count * 3, 32)

        super().__init__(name, parallelism=parallelism)
        self.eval_data = eval_data
        self.criteria_to_be_evaluated = criteria_to_be_evaluated
        self.model_list = model_list
        self.calc_avg_and_std = calc_avg_and_std
        self.logger = logger if logger else logging.getLogger(__name__)
        self.result_type = result_type
        self.custom_prompt_template = custom_prompt_template
        self.evaluation_mode = evaluation_mode

        if prompt_config_path:
            PromptVersionConfig.load_config(prompt_config_path)

        if not self.model_list:
            raise ValueError('Model list cannot be empty. Please provide at least one model.')
        if (
            not self.criteria_to_be_evaluated
            and self.evaluation_mode == EvaluationMode.METRICS
            and not self.custom_prompt_template
        ):
            raise ValueError(
                'Criteria list cannot be empty for metrics evaluation mode without custom_prompt_template.'
            )

        self.logger.info(f'Using {parallelism} concurrent workers for LLM Jury evaluation')

    def setup(self) -> Connector:
        """
        Initialize and sets up a Connector instance. This method creates a Connector object for JURY output.

        Returns
        -------
        Connector with JURY outputs for all sections
        """
        self.output_conn = Connector('jury_output')
        return self.output_conn

    def run(self) -> Connector:
        """Run the LLM evaluation for all sections.

        Returns
        -------
        Connector with evaluation results for all sections
        """
        try:
            self.setup()
            self.logger.info(f'Starting LLM evaluation with {len(self.model_list)} models')
            self.logger.debug(f'Models: {[m.model_id for m in self.model_list]}')
            self.logger.debug(f'Evaluation mode: {self.evaluation_mode}')
            if self.evaluation_mode == EvaluationMode.METRICS:
                self.logger.debug(f'Criteria: {self.criteria_to_be_evaluated}')

            model_list = self.model_list
            processed_sections = 0
            sections_to_process = []
            submitted_futures = []

            # First collect all sections to process
            for stream in self.eval_data.reader():
                sections_to_process.append(stream)

            total_sections = len(sections_to_process)
            self.logger.info(f'Found {total_sections} sections to process')

            # Process each section
            for stream in sections_to_process:
                summary_data = stream.read_json()
                section_id = stream.coords['section_id']
                filename = stream.coords['filename']
                processed_sections += 1

                self.logger.info(f'[{filename}:{section_id}] Processing section {processed_sections}/{total_sections}')
                future = self.submit_task(
                    self.__run_evaluation_per_section,
                    section_id,
                    summary_data,
                    filename,
                    model_list,
                    self.logger,
                    self.result_type,
                    self.custom_prompt_template,
                    self.evaluation_mode,
                    abort_on_error=False,
                )
                if future is not None:
                    submitted_futures.append(future)

            self.logger.info(f'Waiting for all {len(submitted_futures)} submitted evaluations to complete...')

            # Wait for all tasks to complete
            failed_count = 0
            completed_count = 0
            for idx, future in enumerate(submitted_futures, 1):
                try:
                    self.logger.debug(f'Waiting for future {idx}/{len(submitted_futures)}...')
                    future.result(timeout=None)  # Block indefinitely until complete
                    completed_count += 1
                    if idx % 10 == 0 or idx == len(submitted_futures):
                        self.logger.info(f'Progress: {completed_count}/{len(submitted_futures)} sections completed')
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f'Section evaluation failed (future {idx}): {e}', exc_info=True)

            if failed_count > 0:
                self.logger.warning(f'⚠️ {failed_count} out of {total_sections} sections failed during evaluation')
            self.logger.info(f'✅ All evaluations completed: {completed_count} successful, {failed_count} failed')
            return self.output_conn
        finally:
            self._shutdown_executor()

    def __run_evaluation_per_section(
        self,
        section_id: str,
        evaluation_data: dict[str, Any],
        filename: str,
        model_list: list[ChatModelSpec],
        logger: logging.Logger,
        result_type: str | None,
        custom_prompt_template: str | None,
        evaluation_mode: EvaluationMode,
    ) -> None:
        """Process a single section with the LLM evaluator.

        Args
        ----
        section_id : str
            ID of the section
        evaluation_data : dict[str, Any]
            Data to evaluate (can be summary, Q&A, comparison data, etc.)
        filename : str
            Name of the file
        model_list : list[ChatModelSpec]
            List of models to use for evaluation
        result_type : str | None
            Optional result type for the evaluation
        custom_prompt_template : str | None
            Optional custom prompt template for the evaluation
        evaluation_mode : EvaluationMode
            The evaluation mode to use
        """
        # Create log prefix for consistent section/filename context
        log_prefix = f'[{filename}:{section_id}]'

        try:
            self.logger.debug(f'{log_prefix} Starting evaluation')
            self.logger.info(f'{log_prefix} Initializing LLMJURYPerSection')

            evaluation_results = LLMJURYPerSection(
                section_id=section_id,
                filename=filename,
                model_list=model_list,
                evaluation_data=evaluation_data,
                criteria_to_be_evaluated=self.criteria_to_be_evaluated,
                calc_avg_and_std=self.calc_avg_and_std,
                logger=self.logger,
                result_type=result_type,
                custom_prompt_template=custom_prompt_template,
                evaluation_mode=evaluation_mode,
                log_prefix=log_prefix,
            ).run()

            self.logger.info(f'{log_prefix} Successfully completed evaluation')
            evaluation_results_json = evaluation_results.read_json()
            self.output_conn.add_data(evaluation_results_json, section_id=section_id)
            self.logger.debug(f'{log_prefix} Added evaluation results to output connector')

        except KeyError as e:
            self.logger.error(f'{log_prefix} Missing required key {e} in evaluation data', exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f'{log_prefix} Error processing evaluation: {e}', exc_info=True)
            raise
