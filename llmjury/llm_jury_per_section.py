# LLMJury Workbench

import json
import logging
import re
from typing import Any

import numpy as np

from llmjury.chat_invoker import ChatLLMInvoker, LLMWrapper
from llmjury.constants import (
    CALCULATED_SUFFIX,
    CRITERIA_DEFINITION_BASE_DIR,
    JURY_MODEL,
    MAX_REASONABLE_SCORE,
    METRICS_WITHOUT_SOURCE,
    OVERALL_REASONING,
    OVERALL_SCORE,
    PROMPT_BASE_DIR,
    PROMPT_VERSION_SUFFIX,
    REASONING_SUFFIX,
    SCORE_SUFFIX,
    STD_DEV_SUFFIX,
    EvaluationMode,
    PromptFamily,
)
from llmjury.field_mappings import (
    ADDITIONAL_INFO_FIELD_NAMES,
    ANSWER_FIELD_NAMES,
    COMPARISON_FIELD_NAMES_1,
    COMPARISON_FIELD_NAMES_2,
    CONTENT_TYPE_FIELD_NAMES,
    PROMPT_FIELD_NAMES,
    QUESTION_FIELD_NAMES,
    REASONING_FIELD_NAMES,
)
from llmjury.llm_jury_criteria_definition_loader import (
    LLMJURYCriteriaPromptDefinitionLoader,
)
from llmjury.llm_jury_prompt_loader import LLMJURYPromptLoader
from llmjury.prompt_selector import PromptSelector
from llmjury.model_factory import ChatModelSpec
from llmjury.prompt_version_config import PromptVersionConfig
from llmjury.runtime.connector import Connector
from llmjury.runtime.operator import Operator
from llmjury.support.prompt_constants import CONTENT, SYSTEM


class ScoreCalculator:
    """Helper class for calculating scores and statistics."""

    @staticmethod
    def calculate_median(numbers: list[float]) -> float:
        """Calculate the median of a list of numbers."""
        if not numbers:
            return 0.0

        sorted_numbers = sorted(numbers)
        n = len(sorted_numbers)
        return sorted_numbers[n // 2] if n % 2 else (sorted_numbers[n // 2 - 1] + sorted_numbers[n // 2]) / 2

    @staticmethod
    def remove_outlier(numbers: list[float]) -> list[float]:
        """Remove the value furthest from the median."""
        if not numbers:
            return numbers

        # Create a copy of the numbers list
        numbers_copy = numbers.copy()
        median = ScoreCalculator.calculate_median(numbers_copy)
        furthest_element = max(numbers_copy, key=lambda x: abs(x - median))
        numbers_copy.remove(furthest_element)
        return numbers_copy

    @staticmethod
    def calculate_average(numbers: list[float]) -> float:
        """Calculate the average of a list of numbers."""
        if not numbers:
            return 0.0
        return sum(numbers) / len(numbers)

    @staticmethod
    def calculate_standard_deviation(numbers: list[float]) -> float:
        """Calculate the standard deviation of a list of numbers."""
        if not numbers or len(numbers) == 1:
            return 0.0
        return float(np.std(numbers))

    @staticmethod
    def calculate_scores(numbers: list[float]) -> tuple[float, float]:
        """Calculate both average and standard deviation after removing outliers."""
        cleaned_numbers = ScoreCalculator.remove_outlier(numbers)
        average = ScoreCalculator.calculate_average(cleaned_numbers)
        std_dev = ScoreCalculator.calculate_standard_deviation(cleaned_numbers)
        return average, std_dev


class LLMJURYPerSection(Operator):
    """
    Run LLMJURY by invoking the ChatLLM model for given summary.

    Note that all the LLM configuration parameters are defaulted to reasonable values.
    You can modify them as appropriate through LLMWrapper class.

    This workflow uses ChatLLMInvoker Operator which uses LangChain's agenerate() API,
    which asynchronously sends many prompts in parallel, for improved latency.

    Parameters
    ----------
    section_text : str
       The section text to be used.
    summary : str
       The summary associated with the section_text.
    section_id: str
        The section id of the summary that will be attached as a coord to the output connector.
    filename: str
        The file name of the summary that will be attached as a coord to the output connector.
    name : Optional[str], default=None
       An optional additional name or identifier. Defaults to None if not provided.
    calc_avg_and_std: bool, default=True
        Whether to calculate average and standard deviation for jury verdict calculation.
    logger : logging.Logger | None
       Logger to use for logging
    evaluation_data: dict[str, Any]
        The full evaluation data dictionary containing fields like prompt, answer, question, etc.
    log_prefix : str | None, default=None
        Optional log prefix for consistent context. If not provided, will create "[filename:section_id]" format.
    """

    VERSION = '3.0.0'

    # Make the pattern static to avoid recompilation
    _CONTEXT_PATTERN = re.compile(r'(?i)context: @@@(.*?)@@@', re.DOTALL)

    # JSON patterns for finding JSON content in text
    _JSON_PATTERNS = [
        (re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL), 'markdown code block'),
        (re.compile(r'({[\s\S]*})', re.DOTALL), 'raw JSON object'),
    ]

    # Score patterns for extracting scores from text
    _SCORE_PATTERNS = [
        re.compile(r'\bscore\b\s*[:=\-]?\s*([\d.]+)', re.IGNORECASE),  # Flexible 'score' capture
        re.compile(r'score["\s:]+([\d.]+)', re.IGNORECASE),  # Standard score pattern
        re.compile(r'rating["\s:]+([\d.]+)', re.IGNORECASE),  # Alternative rating pattern
        re.compile(r'([\d.]+)\s*(?:out of|/)\s*10', re.IGNORECASE),  # score out of 10
        re.compile(r'([\d.]+)\s*(?:out of|/)\s*5', re.IGNORECASE),  # score out of 5
        re.compile(r'([\d.]+)\s*(?:points?|pts?)', re.IGNORECASE),  # Points pattern
    ]

    # Reasoning patterns for extracting reasoning from text
    _REASONING_PATTERNS = [
        re.compile(r'\breasoning\b\s*[:=\-]?\s*(.*)$', re.IGNORECASE | re.DOTALL),
        re.compile(r'\bexplanation\b\s*[:=\-]?\s*(.*)$', re.IGNORECASE | re.DOTALL),
    ]

    def _clamp_score(self, score: float) -> float:
        """Clamp score to valid range [0, MAX_REASONABLE_SCORE] with warning if exceeded."""
        score = max(0, float(score))
        if score > MAX_REASONABLE_SCORE:
            self.logger.warning(f'Score {score} exceeds max {MAX_REASONABLE_SCORE}, capping')
            return MAX_REASONABLE_SCORE
        return score

    @staticmethod
    def _extract_field_from_dict(data: dict[str, Any], field_names: list[str]) -> str | None:
        """Extract field value from data using prioritized field names."""
        return next((data.get(field) for field in field_names if data.get(field)), None)

    def __init__(
        self,
        section_id: str,
        filename: str,
        model_list: list[ChatModelSpec],
        evaluation_data: dict[str, Any],
        prompt_id: str = 'llm_jury_v2',
        prompt_base_path: str = 'llmJURY',
        criteria_to_be_evaluated: list[str] = ['accuracy', 'truthfulness'],
        name: str | None = None,
        calc_avg_and_std: bool = True,
        logger: logging.Logger | None = None,
        result_type: str | None = None,
        custom_prompt_template: str | None = None,
        evaluation_mode: EvaluationMode = EvaluationMode.METRICS,
        log_prefix: str | None = None,
    ):
        super().__init__(name)
        self.section_id = section_id
        self.filename = filename
        self.evaluation_data = evaluation_data
        self.evaluation_mode = evaluation_mode

        self.logger = logger if logger else logging.getLogger(__name__)

        # Use provided log prefix or create one for consistent section/filename context
        self._log_prefix = log_prefix or f'[{self.filename}:{self.section_id}]'

        # Extract all needed fields from evaluation_data
        self.section_text = self._extract_field_from_dict(evaluation_data, PROMPT_FIELD_NAMES) or ''

        # For summary/answer: Try comparison-specific field names first (summary1, response1, etc.)
        # then fallback to generic answer field names (summary, answer, etc.)
        self.summary = (
            self._extract_field_from_dict(evaluation_data, COMPARISON_FIELD_NAMES_1)
            or self._extract_field_from_dict(evaluation_data, ANSWER_FIELD_NAMES)
            or ''
        )

        self.question = self._extract_field_from_dict(evaluation_data, QUESTION_FIELD_NAMES)
        self.summary2 = self._extract_field_from_dict(evaluation_data, COMPARISON_FIELD_NAMES_2)
        self.content_type = self._extract_field_from_dict(evaluation_data, CONTENT_TYPE_FIELD_NAMES)
        self.additional_info = self._extract_field_from_dict(evaluation_data, ADDITIONAL_INFO_FIELD_NAMES)

        # Get prompt configuration based on evaluation mode and result type
        self.prompt_config = PromptSelector.get_config(result_type, custom_prompt_template, self.evaluation_mode)
        if result_type:
            self.prompt_id = self.prompt_config.jury_prompt_id
        else:
            self.prompt_id = prompt_id

        self.criteria_to_be_evaluated = criteria_to_be_evaluated
        self.prompt_base_path = prompt_base_path
        self.model_list = model_list
        self.calc_avg_and_std = calc_avg_and_std

        if not self.model_list:
            raise ValueError('Model list cannot be empty. Please provide at least one model.')
        if not self.criteria_to_be_evaluated and self.evaluation_mode == EvaluationMode.METRICS:
            raise ValueError('Criteria list cannot be empty for metrics evaluation mode.')

    def setup(self) -> Connector:
        """
        Initialize and set up a Connector instance for all models being run as JURY.

        This method creates a Connector object: 'accuracy_score', "hallucination_score" and 'reasoning'.
        It assigns these Connector objects to instance variables and returns them as JSON objects for each model.

        Returns
        -------
        Connector
            A Connector containing metrics for each model in the following JSON format:
            {
                "model_1": {
                    "accuracy_score": "score of 1 to 5",
                    "accuracy_reasoning":"",
                },
                and so on for all models
            }
        """
        self.jury_results = Connector(name='jury_results', persist_ext='csv')
        return self.jury_results

    def run(self) -> Connector:
        """
        Execute a series of steps to process prompts and obtain LLM responses, then returns a Connector instance.

        Returns
        -------
        Connector
            A Connector containing metrics for each model in the following JSON format:
            {
                "model_1": {
                    "accuracy_score": "Possible 'bias label' values are defined in BiasLabels(Enum)",
                    "hallucination_score": "The reasoning text for the bias label.",
                    "accuracy_reasoning":"",
                    "hallucination_reasoning": ""
                },
               and so on for all the models
            }
        """
        self.setup()
        self.logger.info(f'{self._log_prefix} Starting LLMJURYPerSection evaluation')
        self.logger.debug(f'{self._log_prefix} Number of models: {len(self.model_list)}')
        self.logger.debug(f'{self._log_prefix} Evaluation mode: {self.evaluation_mode}')

        # Process section_text once to handle list input and extract context blocks
        self.section_text = self.extract_context_blocks(self.section_text)

        if self.evaluation_mode == EvaluationMode.METRICS:
            self.logger.debug(f'{self._log_prefix} Criteria to evaluate: {self.criteria_to_be_evaluated}')
            results = self.collate_metrics_results(self.process_summary_input_metrics())
        elif self.evaluation_mode == EvaluationMode.QUESTION_ANSWER:
            # Use 'qna' prefix to clearly identify Q&A mode columns
            results = self.collate_single_score_results(
                self.process_summary_input_question_answer(), 'qna_score', 'qna_reasoning'
            )
        elif self.evaluation_mode == EvaluationMode.COMPARISON:
            # Use 'comparison' prefix to clearly identify comparison mode columns
            results = self.collate_single_score_results(
                self.process_summary_input_comparison(), 'comparison_score', 'comparison_reasoning'
            )
        else:
            raise ValueError(f'Unsupported evaluation mode: {self.evaluation_mode}')
        self.logger.debug(f'{self._log_prefix} Processed summary input for {len(results)} models')

        self.jury_results.add_data(data=results, section_id=self.section_id, filename=self.filename)
        self.logger.info(f'{self._log_prefix} Successfully completed LLMJURYPerSection evaluation')
        return self.jury_results

    def extract_context_blocks(self, string_text: str | list[str]) -> str:
        """Extract all blocks of text that appear between 'CONTEXT: @@@' and '@@@'.

        Also handles list input by converting it to string first.
        """
        # Handle list input by converting to string
        if isinstance(string_text, list):
            self.logger.debug(f'{self._log_prefix} Converting section text from list to string')
            string_text = ' '.join([item for sublist in string_text for item in sublist])
            self.logger.debug(f'{self._log_prefix} Processed section text length: {len(string_text)} characters')

        # Extract context blocks
        matches = self._CONTEXT_PATTERN.findall(string_text)
        return ' '.join(match.strip() for match in matches) if matches else string_text

    def process_summary_input_metrics(self) -> list[dict[str, str]]:
        """Run LLMJury models for the input dictionary having section text, summary details.

        Uses normalized field names:
        - source: Reference/context text (what we evaluate against)
        - response: Model output/summary (what we evaluate)
        """
        self.logger.debug(f'{self._log_prefix} Starting summary input processing')
        results = []

        row = {
            'section_id': self.section_id,
            'filename': self.filename,
            'source': self.section_text,
            'response': self.summary,
        }
        if self.question:
            row['question'] = self.question

        # Iterate over the models and get the results
        for model in self.model_list:
            model_identifier = model.model_name if hasattr(model, 'model_name') else model.model_class.value
            self.logger.info(f'{self._log_prefix} Processing model: {model_identifier}')
            final_result = {}
            llm_eval = self.determine_summary_scores_per_criteria(self.summary, self.section_text, model, self.question)
            row['model'] = model_identifier
            final_result = {**row, **llm_eval}
            results.append(final_result)
            self.logger.debug(f'{self._log_prefix} Completed evaluation for model: {row["model"]}')

        self.logger.info(f'{self._log_prefix} Completed processing for all {len(self.model_list)} models')
        return results

    def process_summary_input_question_answer(self) -> list[dict[str, str]]:
        """Run Q&A evaluation with source detection.

        Uses normalized field names:
        - source: Context/reference text (if available, otherwise question)
        - response: Answer/output
        - question: Question being asked
        """
        has_source = bool(self.section_text and self.section_text.strip())
        self.logger.debug(f'{self._log_prefix} Starting Q&A processing (source available: {has_source})')
        results = []

        if not self.question:
            raise ValueError(
                f'{self._log_prefix} Missing required question field. ' f'Expected one of: {QUESTION_FIELD_NAMES}'
            )

        # Check for custom prompt template
        custom_prompt = self.prompt_config.custom_prompt_template

        # Smart prompt selection based on source availability (done once per section)
        if custom_prompt:
            qa_prompt_id = 'custom'
        else:
            base_prompt_id = PromptSelector.get_question_answer_prompt_id(has_source)
            evaluation_mode = EvaluationMode.QUESTION_ANSWER.value
            qa_version = PromptVersionConfig.get_mode_prompt_version(base_prompt_id, self.content_type, evaluation_mode)
            qa_prompt_id = f'{base_prompt_id}_{qa_version}'

        # Set section_text appropriately based on mode
        section_text_to_use = self.section_text if has_source else self.question

        # Load prompt once per section to extract system prompt for definition
        prompts_list = LLMJURYPromptLoader(
            prompt_id=qa_prompt_id,
            prompt_base_path=f'{PROMPT_BASE_DIR}/{EvaluationMode.QUESTION_ANSWER.value}',
            section_text=section_text_to_use,
            summary=self.summary,
            question=self.question,
            criteria_name='',  # Not needed for QNA
            criteria_definition='',  # Not needed for QNA
            logger=self.logger,
            custom_prompt_template=custom_prompt,
            additional_info=self.additional_info,
        ).run()

        # Extract system prompt for definition
        system_prompt = self._extract_system_prompt(prompts_list)
        qna_definition = f'Prompt ID: {qa_prompt_id}\n\n' f'System Prompt:\n{system_prompt}'

        # Build row based on whether we have source context
        row = {
            'section_id': self.section_id,
            'filename': self.filename,
            'source': self.section_text if has_source else self.question,
            'response': self.summary,
            'question': self.question,
            'qna_definition': qna_definition,
        }

        for model in self.model_list:
            model_identifier = model.model_name if hasattr(model, 'model_name') else model.model_class.value
            self.logger.info(f'{self._log_prefix} Processing Q&A model: {model_identifier}')
            llm_wrapper = self._get_model_wrapper(model)

            # Reuse the prompts_list loaded earlier
            prompts = Connector(name='prompt_connector')
            prompts.write_json(prompts_list.read_json()[0])
            prompts.finished()

            llm_response = ChatLLMInvoker(prompts=prompts, llm_wrapper=llm_wrapper, stream=False, name=self.name).run()
            eval_response = self._process_model_response(llm_response, model)
            validated_response = self._validate_response(eval_response, model)

            llm_eval = {
                'qna_reasoning': validated_response['reasoning'],
                'qna_score': validated_response['score'],
            }
            final_result = {**row, 'model': model_identifier, **llm_eval}
            results.append(final_result)

        return results

    def process_summary_input_comparison(self) -> list[dict[str, str]]:
        """Run a comparison evaluation with smart field detection.

        Handles both:
        1. Summary-to-summary comparison (when summary2 is provided)
        2. Summary-to-ground-truth comparison (when summary2 is not provided)

        Uses normalized field names:
        - source: Reference/context text
        - response_a: First option/summary
        - response_b: Second option/summary (when comparing two outputs)
        - question: Optional question/query being answered (for Q&A comparisons)
        """
        self.logger.debug(f'{self._log_prefix} Starting comparison processing')
        results = []

        # Check for custom prompt template
        custom_prompt = self.prompt_config.custom_prompt_template

        # Determine comparison type based on available data
        if custom_prompt:
            comparison_prompt_id = 'custom'
        elif self.summary2:
            # Summary-to-summary comparison
            family_id = PromptSelector.get_comparison_prompt_id(bool(self.section_text))
            evaluation_mode = EvaluationMode.COMPARISON.value
            comp_version = PromptVersionConfig.get_mode_prompt_version(family_id, self.content_type, evaluation_mode)
            comparison_prompt_id = f'{family_id}_{comp_version}'
        else:
            # Summary-to-ground-truth comparison
            family_id = PromptFamily.COMPARISON_WITH_GROUND_TRUTH.value
            evaluation_mode = EvaluationMode.COMPARISON.value
            comp_version = PromptVersionConfig.get_mode_prompt_version(family_id, self.content_type, evaluation_mode)
            comparison_prompt_id = f'{family_id}_{comp_version}'

        # Load prompt once per section to extract system prompt for definition
        if self.summary2:
            # Summary-to-summary comparison
            prompts_list = LLMJURYPromptLoader(
                prompt_id=comparison_prompt_id,
                prompt_base_path=f'{PROMPT_BASE_DIR}/{EvaluationMode.COMPARISON.value}',
                section_text=self.section_text,
                summary=self.summary,
                summary2=self.summary2,
                question=self.question,
                criteria_name='',
                criteria_definition='',
                logger=self.logger,
                custom_prompt_template=custom_prompt,
                additional_info=self.additional_info,
            ).run()
        else:
            # Summary-to-ground-truth comparison
            prompts_list = LLMJURYPromptLoader(
                prompt_id=comparison_prompt_id,
                prompt_base_path=f'{PROMPT_BASE_DIR}/{EvaluationMode.COMPARISON.value}',
                section_text=self.section_text,  # Ground truth text
                summary=self.summary,  # Answer to compare
                summary2=None,  # No second summary
                question=self.question,
                criteria_name='',
                criteria_definition='',
                logger=self.logger,
                custom_prompt_template=custom_prompt,
                additional_info=self.additional_info,
            ).run()

        # Extract system prompt for definition
        system_prompt = self._extract_system_prompt(prompts_list)
        comparison_definition = f'Prompt ID: {comparison_prompt_id}\n\n' f'System Prompt:\n{system_prompt}'

        # Build row with definition saved once per section, not per model
        if self.summary2:
            # Summary-to-summary comparison
            row = {
                'section_id': self.section_id,
                'filename': self.filename,
                'source': self.section_text,
                'response_a': self.summary,
                'response_b': self.summary2,
                'comparison_definition': comparison_definition,
            }
        else:
            # Summary-to-ground-truth comparison
            row = {
                'section_id': self.section_id,
                'filename': self.filename,
                'source': self.section_text,
                'response_a': self.summary,
                'comparison_definition': comparison_definition,
            }

        # Add question to row if available
        if self.question:
            row['question'] = self.question

        for model in self.model_list:
            model_identifier = model.model_name if hasattr(model, 'model_name') else model.model_class.value
            self.logger.info(f'{self._log_prefix} Processing comparison model: {model_identifier}')
            llm_wrapper = self._get_model_wrapper(model)

            # Reuse the prompts_list loaded earlier
            prompts = Connector(name='prompt_connector')
            prompts.write_json(prompts_list.read_json()[0])
            prompts.finished()

            llm_response = ChatLLMInvoker(
                prompts=prompts,
                llm_wrapper=llm_wrapper,
                stream=False,
                name=self.name,
            ).run()
            eval_response = self._process_model_response(llm_response, model)
            validated_response = self._validate_response(eval_response, model)

            llm_eval = {
                'comparison_reasoning': validated_response['reasoning'],
                'comparison_score': validated_response['score'],
            }
            final_result = {**row, 'model': model_identifier, **llm_eval}
            results.append(final_result)

        return results

    def _process_model_response(self, response: Any, model: ChatModelSpec) -> dict[str, Any]:
        """Process and validate model response, handling various response formats.

        This method handles several response formats:
        1. JSON with score and reasoning fields
        2. JSON with dictionary reasoning
        3. JSON with nested structures
        4. Text with score and reasoning patterns
        5. Raw text responses

        Parameters
        ----------
        response : Any
            The model response to process
        model : ChatModelSpec
            The model factory instance used to generate the response

        Returns
        -------
        dict[str, Any]
            Dictionary containing:
            - score: float (0-100 range, supports scales like 1-5, 1-10, 1-100)
            - reasoning: str (explanation for the score)
        """
        try:
            text_content = self._extract_text_content(response)
            self.logger.debug(f'Raw model response: {text_content}')

            # Try JSON parsing first
            if json_result := self._parse_json_content(text_content):
                if json_result['score'] > 0 or json_result['reasoning']:
                    return json_result

            # Fall back to text pattern matching
            return self._parse_text_patterns(text_content)

        except Exception as e:
            self.logger.error(f'Error processing model response: {str(e)}')
            return {
                'score': 0,
                'reasoning': text_content if 'text_content' in locals() else 'Error processing response',
            }

    def _extract_text_content(self, response: Any) -> str:
        """Extract text content from response object.

        Parameters
        ----------
        response : Any
            The model response to extract text from finished Connector

        Returns
        -------
        str
            The extracted text content

        Raises
        ------
        AttributeError, IOError
            If text content cannot be extracted
        """
        try:
            # ChatLLMInvoker returns a finished Connector in non-streaming mode
            # Use all_text() to get all text from the finished Connector
            text: str = response.all_text()
            return text
        except (AttributeError, OSError) as e:
            self.logger.error(f'Failed to read response text: {str(e)}')
            raise

    def _parse_json_content(self, text_content: str) -> dict[str, Any] | None:
        """Parse JSON content from text and extract score and reasoning.

        Parameters
        ----------
        text_content : str
            The text content to parse for JSON

        Returns
        -------
        dict[str, Any] | None
            Dictionary containing score and reasoning if JSON was successfully parsed,
            None otherwise
        """
        if not (json_content := self._find_json_content(text_content)):
            return None

        try:
            parsed_json = self._parse_and_clean_json(json_content)
            # Some providers wrap response under keys like 'content', 'data'
            if isinstance(parsed_json, dict) and 'content' in parsed_json and isinstance(parsed_json['content'], dict):
                candidate = parsed_json['content']
                extracted = self._extract_json_fields(candidate)
                if extracted.get('score', 0) or extracted.get('reasoning'):
                    return extracted
            return self._extract_json_fields(parsed_json)
        except json.JSONDecodeError as e:
            self.logger.warning(f'Invalid JSON in response: {str(e)}')
            return None

    def _find_json_content(self, text_content: str) -> str | None:
        """Find JSON content in text using various patterns.

        Parameters
        ----------
        text_content : str
            The text content to search for JSON

        Returns
        -------
        str | None
            The found JSON content or None if no JSON was found
        """
        for pattern, pattern_type in self._JSON_PATTERNS:
            if match := pattern.search(text_content):
                self.logger.debug(f'Found JSON content in {pattern_type}')
                return match.group(1)
        return None

    def _parse_and_clean_json(self, json_content: str) -> dict[str, Any]:
        """Parse and clean JSON content."""
        sanitized_json = re.sub(r'[\x00-\x1F\x7F]', '', json_content)
        parsed_json = json.loads(sanitized_json)

        if isinstance(parsed_json, list):
            if not parsed_json:
                return {}
            first_item = parsed_json[0]
            return first_item if isinstance(first_item, dict) else {'value': first_item}
        return parsed_json if isinstance(parsed_json, dict) else {'value': parsed_json}

    def _extract_json_fields(self, parsed_json: dict[str, Any]) -> dict[str, Any]:
        """Extract score and reasoning from parsed JSON.

        Parameters
        ----------
        parsed_json : dict[str, Any]
            The parsed JSON content

        Returns
        -------
        dict[str, Any]
            Dictionary containing score and reasoning
        """
        result = {'score': 0, 'reasoning': ''}

        # Extract score using multiple strategies
        if 'score' in parsed_json:
            score_value = parsed_json['score']
            if isinstance(score_value, (int, float)):
                result['score'] = self._clamp_score(score_value)
        else:
            for value in parsed_json.values():
                if isinstance(value, (int, float)):
                    result['score'] = self._clamp_score(value)
                    break
                elif isinstance(value, dict) and 'score' in value:
                    score_value = value['score']
                    if isinstance(score_value, (int, float)):
                        result['score'] = self._clamp_score(score_value)
                        break

        # Extract reasoning using multiple strategies
        if 'reasoning' in parsed_json:
            result['reasoning'] = self._format_reasoning(parsed_json['reasoning'])
        else:
            for key, value in parsed_json.items():
                if key.lower() in REASONING_FIELD_NAMES:
                    result['reasoning'] = self._format_reasoning(value)
                    break
                elif isinstance(value, dict):
                    for k, v in value.items():
                        if k.lower() in REASONING_FIELD_NAMES:
                            result['reasoning'] = self._format_reasoning(v)
                            break

        return result

    def _format_reasoning(self, reasoning: str | dict[str, Any]) -> str:
        """Format reasoning into a string.

        Parameters
        ----------
        reasoning : str | dict[str, Any]
            The reasoning to format

        Returns
        -------
        str
            The formatted reasoning
        """
        if isinstance(reasoning, dict):
            reasoning_parts: list[str] = [
                f'{key}: {value}' for key, value in reasoning.items() if not isinstance(value, (int, float))
            ]
            return '\n'.join(reasoning_parts) if reasoning_parts else str(reasoning)
        return str(reasoning)

    def _parse_text_patterns(self, text_content: str) -> dict[str, Any]:
        """Extract score and reasoning from text patterns.

        Parameters
        ----------
        text_content : str
            The text content to parse

        Returns
        -------
        dict[str, Any]
            Dictionary containing score and reasoning
        """
        score = self._extract_score_from_text(text_content)
        reasoning = self._extract_reasoning_from_text(text_content)
        return {'score': score, 'reasoning': reasoning or text_content.strip()}

    def _extract_score_from_text(self, text_content: str) -> float:
        """Extract score from text using various patterns.

        Parameters
        ----------
        text_content : str
            The text content to parse

        Returns
        -------
        float
            The extracted score (0-100 range, capped as safeguard against LLM errors)
        """
        for pattern in self._SCORE_PATTERNS:
            if score_match := pattern.search(text_content):
                try:
                    return self._clamp_score(float(score_match.group(1)))
                except (ValueError, TypeError):
                    continue
        return 0.0

    def _extract_reasoning_from_text(self, text_content: str) -> str:
        """Extract reasoning from text using various patterns.

        Parameters
        ----------
        text_content : str
            The text content to parse

        Returns
        -------
        str
            The extracted reasoning
        """
        for pattern in self._REASONING_PATTERNS:
            if reasoning_match := pattern.search(text_content):
                return reasoning_match.group(1).strip()
        return ''

    def _validate_response(self, response: dict[str, Any], model: ChatModelSpec) -> dict[str, Any]:
        """Validate and normalize the response structure."""
        if not isinstance(response, dict):
            self.logger.warning(f'Unexpected response type from {model.model_class.value}: {type(response)}')
            return {'reasoning': str(response), 'score': 0}

        response.setdefault('reasoning', 'No reasoning provided')
        response.setdefault('score', 0)

        try:
            response['score'] = float(response['score'])
        except (ValueError, TypeError):
            self.logger.warning(f'Invalid score value from {model.model_class.value}: {response["score"]}')
            response['score'] = 0

        return response

    def _get_model_wrapper(self, model: ChatModelSpec) -> LLMWrapper:
        """Get configured model wrapper based on model type.

        Args
        ----
        model : ChatModelSpec
            The model factory instance

        Returns
        -------
        LLMWrapper
            Configured LLMWrapper instance

        Raises
        ------
        ValueError
            If model type is not supported
        """
        model_name = getattr(model, 'model_name', '').lower()
        use_json_format = False

        if 'gpt' in model_name and self.evaluation_mode == EvaluationMode.METRICS:
            custom_prompt = self.prompt_config.custom_prompt_template
            # Use JSON format only if: no custom prompt OR custom prompt mentions "json"
            use_json_format = not custom_prompt or 'json' in custom_prompt.lower()

        if use_json_format:
            model_kwargs = {'response_format': {'type': 'json_object'}}
            return model.get_llm_wrapper(model_kwargs=model_kwargs)
        return model.get_llm_wrapper()

    def _extract_system_prompt(self, prompts_list: Connector) -> str:
        """Extract the system prompt from LLMJURYPromptLoader result.

        Parameters
        ----------
        prompts_list : Connector
            The Connector returned by LLMJURYPromptLoader.run()

        Returns
        -------
        str
            The system prompt content (empty string if not found)
        """
        try:
            prompt_data = prompts_list.read_json()[0]
            # First message in the list is the SYSTEM message
            for msg in prompt_data:
                if msg.get('type') == SYSTEM:
                    content = msg.get(CONTENT, '')
                    return str(content) if content else ''
            return ''
        except (IndexError, KeyError, TypeError) as e:
            self.logger.warning(f'Could not extract system prompt: {str(e)}')
            return ''

    def determine_summary_scores_per_criteria(
        self, summary: str, section_text: str, model: ChatModelSpec, question: str | None
    ) -> dict[Any, Any]:
        """Load the prompts for each criteria and make LLM Calls."""
        model_identifier = model.model_name if hasattr(model, 'model_name') else model.model_class.value
        self.logger.debug(f'{self._log_prefix} Starting criteria evaluation for model: {model_identifier}')
        llm_eval: dict[str, Any] = {}
        # Store per-criteria definition text and resolved version to later emit in output
        criteria_meta: dict[str, dict[str, Any]] = {}

        try:
            # Configure model wrapper
            llm_wrapper = self._get_model_wrapper(model)

            # Load criteria definitions and capture definition text + resolved versions
            for criteria in self.criteria_to_be_evaluated:
                try:
                    # Get prompt version based on content type and evaluation mode
                    if hasattr(PromptVersionConfig, 'PROMPT_MAPPINGS') and PromptVersionConfig.PROMPT_MAPPINGS:
                        # Pass evaluation_data for optional customization (e.g., summary_customization_length)
                        full_prompt_version = PromptVersionConfig.get_prompt_version(
                            criteria, self.content_type, self.evaluation_mode.value, self.evaluation_data
                        )
                    else:
                        # Use default from prompt selector config
                        full_prompt_version = self.prompt_config.criteria_definition_id_template.format(
                            criteria=criteria
                        )

                    used_version = full_prompt_version
                    try:
                        # Attempt to load the specific versioned prompt first
                        self.logger.debug(
                            f'Attempting to load prompt version: {full_prompt_version} for criteria: {criteria}'
                        )
                        prompts_list = LLMJURYCriteriaPromptDefinitionLoader(
                            prompt_id=f'{criteria}_definition_{full_prompt_version}',
                            prompt_base_path=f'{CRITERIA_DEFINITION_BASE_DIR}/{criteria}',
                            criteria_name=str(criteria),
                            logger=self.logger,
                            name=f'LLMJURY{criteria}DefinitionLoader',
                        ).run()
                    except Exception as e:
                        # If the specific version fails, fall back to the base version
                        base_version = full_prompt_version.split('_')[0]
                        used_version = base_version
                        self.logger.warning(
                            f"Failed to load prompt version '{full_prompt_version}' for criteria '{criteria}'. "
                            f"Falling back to base version '{base_version}'. Error: {e}"
                        )
                        prompts_list = LLMJURYCriteriaPromptDefinitionLoader(
                            prompt_id=f'{criteria}_definition_{base_version}',
                            prompt_base_path=f'{CRITERIA_DEFINITION_BASE_DIR}/{criteria}',
                            criteria_name=str(criteria),
                            logger=self.logger,
                            name=f'LLMJURY{criteria}DefinitionLoader',
                        ).run()
                    definition_text = prompts_list.all_text()
                    # Persist meta for later: definition text and resolved prompt id/version
                    criteria_meta[str(criteria)] = {
                        'definition_text': definition_text,
                        'used_version': used_version,
                    }
                    self.logger.debug(f'{self._log_prefix} Successfully loaded criteria definition for: {criteria}')
                except Exception as e:
                    self.logger.error(
                        f'{self._log_prefix} Failed to load criteria definition for {criteria}: {str(e)}', exc_info=True
                    )
                    continue

            # Process each criteria
            for criteria_name, meta in criteria_meta.items():
                try:
                    self.logger.info(f'{self._log_prefix} Evaluating criteria: {criteria_name}')
                    criteria_definition = meta['definition_text']
                    section_text_to_use = '' if criteria_name in METRICS_WITHOUT_SOURCE else section_text

                    # Get prompt version for LLM jury based on content type and evaluation mode
                    if hasattr(PromptVersionConfig, 'PROMPT_MAPPINGS') and PromptVersionConfig.PROMPT_MAPPINGS:
                        # Pass evaluation_data for optional customization (e.g., summary_customization_length)
                        llm_jury_prompt_version = PromptVersionConfig.get_prompt_version(
                            'llm_jury', self.content_type, self.evaluation_mode.value, self.evaluation_data
                        )
                        llm_jury_prompt_id = f'llm_jury_{llm_jury_prompt_version}'
                    else:
                        llm_jury_prompt_id = self.prompt_id

                    self.logger.debug(f'Using LLM jury prompt id: {llm_jury_prompt_id}')
                    prompts_list = LLMJURYPromptLoader(
                        prompt_id=llm_jury_prompt_id,
                        prompt_base_path=f'{PROMPT_BASE_DIR}/{EvaluationMode.METRICS.value}',
                        section_text=section_text_to_use,
                        summary=summary,
                        criteria_name=criteria_name,
                        criteria_definition=criteria_definition,
                        logger=self.logger,
                        name='LLMJURYPromptLoader',
                        custom_prompt_template=self.prompt_config.custom_prompt_template,
                        question=question,
                        content_type=self.content_type,
                        additional_info=self.additional_info,
                    ).run()

                    # Extract system prompt for better understanding
                    system_prompt = self._extract_system_prompt(prompts_list)

                    prompts = Connector(name='prompt_connector')
                    for prompt_instance_index, prompt_instance in enumerate(prompts_list.read_json()):
                        prompts.write_json(prompt_instance, index=prompt_instance_index)
                    prompts.finished()

                    # Get and process model response
                    self.logger.debug(f'{self._log_prefix} Invoking LLM for criteria: {criteria_name}')

                    llm_response = ChatLLMInvoker(
                        prompts=prompts,
                        llm_wrapper=llm_wrapper,
                        stream=False,
                        name=self.name,
                    ).run()

                    eval_response = self._process_model_response(llm_response, model)
                    eval_response = self._validate_response(eval_response, model)

                    llm_eval[criteria_name + '_reasoning'] = eval_response['reasoning']
                    llm_eval[criteria_name + '_score'] = eval_response['score']

                    # Save criteria ID, prompt ID, and system prompt
                    criteria_used_version: str = str(meta.get('used_version', 'v2'))
                    criteria_id = f'{criteria_name}_definition_{criteria_used_version}'
                    llm_eval[criteria_name + '_definition'] = (
                        f'Criteria ID: {criteria_id}\n'
                        f'Prompt ID: {llm_jury_prompt_id}\n\n'
                        f'System Prompt:\n{system_prompt}'
                    )

                except Exception as e:
                    self.logger.error(
                        f'{self._log_prefix} Failed to process criteria {criteria_name}: {str(e)}', exc_info=True
                    )
                    llm_eval[criteria_name + '_reasoning'] = f'Error processing criteria: {str(e)}'
                    llm_eval[criteria_name + '_score'] = 0

        except Exception as e:
            self.logger.error(
                f'{self._log_prefix} Critical error in determine_summary_scores_per_criteria: {str(e)}', exc_info=True
            )
            raise

        self.logger.info(f'{self._log_prefix} Completed all criteria evaluations for model: {model_identifier}')
        return llm_eval

    def consolidate_reasoning(self, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        """Consolidate reasoning from different LLMs into a comprehensive analysis and get a score.

        Args
        ----
        evaluations : list[dict[str, Any]]
            List of dictionaries containing evaluation details in the format:
            [
                {
                    'axis': str,  # The evaluation criteria/axis name
                    'score': float,  # The score for this axis
                    'reasoning': str  # The reasoning for this score
                },
                ...
            ]

        Returns
        -------
        dict[str, Any]
            Dictionary containing consolidated reasoning and score
        """
        if not self.model_list:
            self.logger.warning(f'{self._log_prefix} No models available for consolidation')
            return {'reasoning': 'Unable to consolidate reasoning - no models available', 'score': 0}

        try:
            # Format evaluations text; mark excluded (score<=0) evaluations
            formatted_blocks: list[str] = []
            for i, e in enumerate(evaluations, 1):
                excluded_note = ' (EXCLUDED: score=0, not used in average)' if float(e.get('score', 0)) <= 0 else ''
                formatted_blocks.append(
                    f'Evaluation {i}:\nAxis: {e["axis"]}{excluded_note}\n'
                    f'score: {e["score"]}\nReasoning: {e["reasoning"]}'
                )
            evaluations_text = '\n\n'.join(formatted_blocks)

            # Load and process consolidation prompt
            prompts_list = LLMJURYPromptLoader(
                prompt_id=self.prompt_config.consolidation_prompt_id,
                prompt_base_path=f'{PROMPT_BASE_DIR}/{PromptFamily.CONSOLIDATION.value.replace("_prompt", "")}',
                section_text=evaluations_text,
                summary='',
                criteria_name='ReasoningConsolidation',
                criteria_definition='',
                logger=self.logger,
                name='ConsolidationPromptLoader',
                additional_info=self.additional_info,
            ).run()

            # Convert prompts to Connector
            prompts = Connector(name='consolidation_prompt_connector')
            for i, prompt in enumerate(prompts_list.read_json()):
                prompts.write_json(prompt, index=i)
            prompts.finished()

            # Get model wrapper for consolidation
            # Use the first model from model_list to consolidate the reasoning
            model = self.model_list[0]
            llm_wrapper = self._get_model_wrapper(model)
            consolidated_response = ChatLLMInvoker(
                prompts=prompts,
                llm_wrapper=llm_wrapper,
                stream=False,
                name='ConsolidationInvoker',
            ).run()

            response_data = self._process_model_response(consolidated_response, model)
            return self._validate_response(response_data, model)
        except Exception as e:
            self.logger.error(f'{self._log_prefix} Error consolidating reasoning: {str(e)}', exc_info=True)
            return {'reasoning': 'Error consolidating reasoning', 'score': 0}

    def collate_metrics_results(self, results: list[dict[Any, Any]]) -> list[dict[Any, Any]]:
        """Post process the LLM responses to collate them in desired output format and also calculate LLMJURY score."""
        new_data: dict[Any, Any] = {}

        # Group results by section_id
        for item in results:
            section_id = item['section_id']
            if section_id not in new_data:
                new_data[section_id] = []
            data = {k: v for k, v in item.items()}
            new_data[section_id].append(data)

        flat_results = []

        # For multiple models, first calculate jury verdict
        if len(self.model_list) > 1:
            new_data = self.calculate_jury_verdict_and_confidence(new_data)

        # Calculate overall score and update entries
        for _section_id, entries in new_data.items():
            overall_evaluation = self.calculate_overall_score(entries)
            for entry in entries:
                # For multiple models, only update Jury 2.0 entries
                # For single model, update all entries
                if len(self.model_list) == 1 or entry.get('model') == JURY_MODEL:
                    entry.update(overall_evaluation)
                flat_results.append(entry)

        return flat_results

    def calculate_jury_verdict_and_confidence(self, new_data: dict[Any, Any]) -> dict[Any, Any]:
        """Calculate JURY score by taking scores from different LLMs."""
        for _sequence_id, list_data in new_data.items():
            # Initialize final entry with metadata from first entry
            final_entry = {
                k: v
                for k, v in list_data[0].items()
                if not (k.endswith(SCORE_SUFFIX) or k.endswith(REASONING_SUFFIX) or k.endswith(PROMPT_VERSION_SUFFIX))
            }

            # Initialize collectors for scores, reasons, and prompt versions
            score_collectors: dict[str, list[float]] = {}
            reason_collectors: dict[str, list[str]] = {}
            prompt_version_collectors: dict[str, list[str]] = {}

            # Collect all scores and reasons from each model
            for entry in list_data:
                for key, value in entry.items():
                    if key.endswith(SCORE_SUFFIX):
                        if key not in score_collectors:
                            score_collectors[key] = []
                        # Ensure we're collecting floats
                        if isinstance(value, (int, float)):
                            score_collectors[key].append(float(value))
                        elif isinstance(value, list):
                            score_collectors[key].extend([float(v) for v in value])
                    elif key.endswith(REASONING_SUFFIX):
                        if key not in reason_collectors:
                            reason_collectors[key] = []
                        if isinstance(value, str):
                            reason_collectors[key].append(value)
                        elif isinstance(value, list):
                            reason_collectors[key].extend(value)
                    elif key.endswith(PROMPT_VERSION_SUFFIX):
                        if key not in prompt_version_collectors:
                            prompt_version_collectors[key] = []
                        if isinstance(value, str):
                            prompt_version_collectors[key].append(value)
                        elif isinstance(value, list):
                            prompt_version_collectors[key].extend(value)

            # Loop through score and reason collectors together
            for score_key, scores in score_collectors.items():
                reason_key = score_key.replace(SCORE_SUFFIX, REASONING_SUFFIX)
                reasons = reason_collectors.get(reason_key, [])

                if scores and reasons:  # Only process if we have both scores and reasons
                    # Exclude zero/invalid scores from numeric aggregation
                    included_scores = [s for s in scores if isinstance(s, (int, float)) and float(s) > 0]
                    if self.calc_avg_and_std:
                        # Calculate jury score and confidence
                        jury_score, confidence = (
                            self.calculate_avg_and_std(included_scores) if included_scores else (0, 0)
                        )
                        calculated_score_key = score_key.replace(SCORE_SUFFIX, CALCULATED_SUFFIX)
                        final_entry[calculated_score_key] = jury_score
                        conf_key = score_key.replace(SCORE_SUFFIX, STD_DEV_SUFFIX)
                        final_entry[conf_key] = confidence

                    # Create evaluation list with axis information
                    evaluations = [
                        {'axis': reason_key.replace(REASONING_SUFFIX, ''), 'score': score, 'reasoning': reason}
                        for reason, score in zip(reasons, scores)
                    ]

                    # Consolidate reasons and scores from LLMJURY
                    consolidated_result = self.consolidate_reasoning(evaluations)
                    final_entry[reason_key] = consolidated_result['reasoning']
                    final_entry[score_key] = consolidated_result['score']

                    # Preserve prompt version information (use the most common version or first one)
                    prompt_version_key = score_key.replace(SCORE_SUFFIX, PROMPT_VERSION_SUFFIX)
                    if (
                        prompt_version_key in prompt_version_collectors
                        and prompt_version_collectors[prompt_version_key]
                    ):
                        # Use the first prompt version as representative
                        final_entry[prompt_version_key] = prompt_version_collectors[prompt_version_key][0]

            final_entry['model'] = JURY_MODEL

            # Append the jury verdict to the list of entries
            list_data.append(final_entry)

        return new_data

    def calculate_avg_and_std(self, scores: list[float]) -> tuple[Any, float]:
        """Calculate the average and standard deviation of the different model scores."""
        return ScoreCalculator.calculate_scores(scores)

    def calculate_overall_score(self, results: list[dict[Any, Any]]) -> dict[str, Any]:
        """Calculate an overall score by considering all metrics across all files.

        This method calculates an overall score across all metrics. For multiple models,
        it uses the consolidated Jury model responses. For single model, it uses
        the model's responses directly.

        Args
        ----
        results : list[dict[Any, Any]]
            List of dictionaries containing evaluation results from different models.
            For multiple models, only entries with model=JURY_MODEL are processed.
            For single model, all entries are processed.

        Returns
        -------
        dict[str, Any]
            Dictionary containing:
            - overall_score: The consolidated score from all metrics
            - overall_reasoning: Consolidated reasoning for the overall score
        """
        try:
            # Skip overall score calculation if only one criteria is being evaluated
            if len(self.criteria_to_be_evaluated) <= 1:
                self.logger.info(
                    f'{self._log_prefix} Skipping overall score calculation - only one criteria being evaluated'
                )
                return {}

            # Collect evaluations using list comprehension
            evaluations: list[dict[str, Any]] = [
                {
                    'axis': key.replace(SCORE_SUFFIX, ''),
                    'score': float(value),
                    'reasoning': result.get(key.replace(SCORE_SUFFIX, REASONING_SUFFIX), ''),
                }
                for result in results
                if len(self.model_list) == 1 or result.get('model') == JURY_MODEL
                for key, value in result.items()
                if key.endswith(SCORE_SUFFIX) and isinstance(value, (int, float))
            ]

            if not evaluations:
                self.logger.warning(f'{self._log_prefix} No valid evaluations found for overall score')
                return {
                    OVERALL_SCORE: 0,
                    OVERALL_REASONING: 'No reasoning available for overall score',
                }

            # Consolidate all reasoning and get overall score
            consolidated_result = self.consolidate_reasoning(evaluations)
            self.logger.info(f'{self._log_prefix} Overall score: {consolidated_result["score"]}')

            return {
                OVERALL_SCORE: consolidated_result['score'],
                OVERALL_REASONING: consolidated_result['reasoning'],
            }

        except Exception as e:
            self.logger.error(f'{self._log_prefix} Error calculating overall score: {str(e)}', exc_info=True)
            return {
                OVERALL_SCORE: 0,
                OVERALL_REASONING: 'Error calculating overall score',
            }

    def collate_single_score_results(
        self, results: list[dict[str, Any]], score_key: str, reasoning_key: str
    ) -> list[dict[str, Any]]:
        """Collate results for single-score evaluation modes (Question Answer, Comparison).

        - When multiple models are present: add a Jury entry averaging scores and concatenating reasonings.
        - Set overall_score and overall_reasoning based on the final verdict for easy reporting.
        - When a single model is present: set overall fields on that single result.
        """
        if not results:
            return results

        # Multiple models → add jury entry
        if len(self.model_list) > 1:
            scores = [r.get(score_key, 0) for r in results if score_key in r]
            included_scores = [s for s in scores if isinstance(s, (int, float)) and float(s) > 0]
            reasonings = [r.get(reasoning_key, '') for r in results if reasoning_key in r]

            jury_entry = results[0].copy()
            jury_entry['model'] = JURY_MODEL
            jury_entry[score_key] = ScoreCalculator.calculate_average(included_scores) if included_scores else 0
            jury_entry[reasoning_key] = '\n\n---\n\n'.join(
                f'Model {i+1} Reasoning:\n{r}' for i, r in enumerate(reasonings)
            )
            results.append(jury_entry)

            # Only set overall fields for METRICS mode with multiple criteria
            # For Q&A and Comparison, the score/reasoning fields are already the final verdict
            if self.evaluation_mode == EvaluationMode.METRICS and len(self.criteria_to_be_evaluated) > 1:
                jury_entry[OVERALL_SCORE] = jury_entry.get(score_key, 0)
                jury_entry[OVERALL_REASONING] = jury_entry.get(reasoning_key, '')

        # For single model with multiple criteria in METRICS mode, set overall fields
        if (
            len(self.model_list) <= 1
            and self.evaluation_mode == EvaluationMode.METRICS
            and len(self.criteria_to_be_evaluated) > 1
        ):
            single = results[0]
            single[OVERALL_SCORE] = single.get(score_key, 0)
            single[OVERALL_REASONING] = single.get(reasoning_key, '')

        return results
