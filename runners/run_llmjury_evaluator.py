#
#    ADOBE CONFIDENTIAL
#    ___________________
#
#    Copyright 2025 Adobe
#    All Rights Reserved.
#
#    NOTICE:  All information contained herein is, and remains
#    the property of Adobe and its suppliers, if any. The intellectual
#    and technical concepts contained herein are proprietary to Adobe
#    and its suppliers and are protected by all applicable intellectual
#    property laws, including trade secret and copyright laws.
#    Dissemination of this information or reproduction of this material
#    is strictly forbidden unless prior written permission is obtained
#    from Adobe.
#
"""
LLM Multi-Mode Evaluation Runner.

Runs LLM-based evaluation in specified mode (METRICS, QUESTION_ANSWER, COMPARISON).
Processes JSON evaluation data and generates formatted Excel reports with multiple sheets.
"""

import argparse
import json
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llmjury.env_bootstrap import load_llmjury_env

load_llmjury_env()

import pandas as pd

from llmjury.constants import EvaluationCriteria, EvaluationMode, SheetName
from llmjury.model_factory import ChatModelSpec
from llmjury.runtime.connector import Connector
from llmjury.runtime.session import Session
from llmjury.excel_persister import LLMJuryExcelPersister
from llmjury.llm_jury_results_transformer import LLMJuryResultsTransformer
from llmjury.llmjury_evaluator import LLMJuryEvaluator
from llmjury.meta_analyzer import LLMJuryMetaAnalyzer
from llmjury.model_factory import get_model
from llmjury.report_generator import LLMJuryReportGenerator

# Suppress specific warnings
warnings.filterwarnings('ignore', category=UserWarning, module='langchain_openai')
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic._internal._config')

# Get logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class EvaluationConfig:
    """Configuration for evaluation run."""

    eval_json_path: Path
    criteria: list[str]
    models: list[str]
    name: str = ''
    calc_avg_and_std: bool = True
    prompt_config_path: str | None = None
    result_type: str | None = None
    custom_prompt_template: str | None = None
    evaluation_mode: EvaluationMode = EvaluationMode.METRICS
    enable_meta_analysis: bool = False
    meta_score_threshold: float = 3.5
    meta_prompt_config: str | None = None
    meta_custom_prompt: str | None = None


def process_file(file_path: Path) -> dict[str, Any]:
    """
    Process a single JSON file and return its contents.

    Args:
        file_path: Path to the JSON file to process

    Returns:
        Dictionary containing the processed file contents

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    try:
        with open(file_path, encoding='utf-8') as f:
            return {file_path.stem: json.load(f)}
    except FileNotFoundError:
        logger.error(f'File not found: {file_path}')
        raise
    except json.JSONDecodeError as e:
        logger.error(f'Invalid JSON in file {file_path}: {e}')
        raise
    except Exception as e:
        logger.error(f'Error processing file {file_path}: {e}')
        raise


def add_dict_as_json_file(data: list[dict[str, Any]], filename: str, folder_path: Path) -> None:
    """
    Save data as a JSON file.

    Args:
        data: Data to save
        filename: Name of the file (with or without .json extension)
        folder_path: Path to the folder where the file should be saved

    Raises:
        OSError: If there are issues with file operations
        json.JSONDecodeError: If data cannot be serialized to JSON
    """
    try:
        if not filename.endswith('.json'):
            filename = f'{filename}.json'

        file_path = folder_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        logger.info(f'Successfully saved JSON file: {file_path}')
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f'Error saving JSON file {filename}: {e}')
        raise


def llm_evaluator(
    eval_json_path: Path,
    criteria_to_be_evaluated: list[str] | None = None,
    models: list[str] | None = None,
    name: str = '',
    calc_avg_and_std: bool = True,
    prompt_config_path: str | None = None,
    result_type: str | None = None,
    custom_prompt_template: str | None = None,
    evaluation_mode: EvaluationMode = EvaluationMode.METRICS,
    enable_meta_analysis: bool = False,
    meta_score_threshold: float = 3.5,
    meta_prompt_config: str | None = None,
    meta_custom_prompt: str | None = None,
) -> None:
    """
    Run LLM-based evaluation in the specified mode.

    Args:
        eval_json_path: Path to JSON file(s) to evaluate
        criteria_to_be_evaluated: Evaluation criteria list. For METRICS mode without custom_prompt,
            defaults to [accuracy, comprehensiveness, conciseness, duplicacy, fluency, navigation, truthfulness].
            Not required for QNA/COMPARISON modes or when using custom_prompt_template.
        models: List of model names. If None, uses default models:
            ['gpt_4o_mini', 'gpt_5_mini']
        name: Optional suffix for output files
        calc_avg_and_std: Calculate average and standard deviation
        prompt_config_path: Optional prompt config file path
        result_type: Optional result type
        custom_prompt_template: Optional custom prompt
        evaluation_mode: Evaluation mode (METRICS, QUESTION_ANSWER, or COMPARISON)
        enable_meta_analysis: Generate executive summary via meta-analysis (METRICS mode only)
        meta_score_threshold: Score threshold for meta-analysis concerning files (default: 3.5)
        meta_prompt_config: Prompt config for meta-analysis (e.g., 'meta_analysis_v1')
        meta_custom_prompt: Custom prompt template for meta-analysis
    """
    # Set default criteria if not provided (comprehensive set for quality evaluation)
    if criteria_to_be_evaluated is None:
        if custom_prompt_template:
            # Use dummy 'custom' criteria - the custom_prompt_template will handle everything
            criteria_to_be_evaluated = ['custom']
            logger.info('📋 Using custom prompt with generic "custom" criteria')
        else:
            criteria_to_be_evaluated = [
                EvaluationCriteria.ACCURACY.value,
                EvaluationCriteria.COMPREHENSIVENESS.value,
                EvaluationCriteria.CONCISENESS.value,
                EvaluationCriteria.DUPLICACY.value,
                EvaluationCriteria.FLUENCY.value,
                EvaluationCriteria.NAVIGATION.value,
                EvaluationCriteria.TRUTHFULNESS.value,
                EvaluationCriteria.ANALOGY.value,
                EvaluationCriteria.ENGAGEMENT.value,
                EvaluationCriteria.USEFULNESS.value,
                EvaluationCriteria.TONALITY.value,
                EvaluationCriteria.CLARITY.value,
                EvaluationCriteria.COHERENCE.value,
                EvaluationCriteria.BALANCE.value,
                EvaluationCriteria.DIVERSITY.value,
            ]
            logger.info(f'📋 Using default criteria: {criteria_to_be_evaluated}')

    # Set default models if not provided
    if models is None:
        models = ['gpt_4o_mini', 'gpt_5_mini']
        logger.info(f'Using default models: {models}')

    # Load models and handle failures
    model_list: list[ChatModelSpec] = []
    failed_models = []
    for model_name in models:
        try:
            model_list.append(get_model(model_name))
            logger.info(f'✅ Loaded model: {model_name}')
        except ValueError as e:
            failed_models.append(model_name)
            logger.error(f'❌ Failed to load "{model_name}": {e}')

    if not model_list:
        raise ValueError(f'No valid models loaded. Failed models: {failed_models}')

    if failed_models:
        logger.warning(f'⚠️ Continuing with {len(model_list)} models (failed: {failed_models})')

    logger.info(f'📁 Loading evaluation data from: {eval_json_path}')

    # Load JSON files
    eval_json_result_dataset = {}
    if eval_json_path.is_file():
        eval_json_result_dataset = process_file(eval_json_path)
    else:
        for file_path in eval_json_path.glob('*.json'):
            eval_json_result_dataset.update(process_file(file_path))

    if not eval_json_result_dataset:
        raise ValueError('No valid JSON files found')

    logger.info(f'✅ Loaded {len(eval_json_result_dataset)} files')
    logger.info(f'📊 Evaluation mode: {evaluation_mode.value}')

    # Run evaluation
    results: list[dict[str, Any]] = []
    output_folder = eval_json_path.parent
    output_name = f"llm_evaluation_results{'_' + name if name else ''}"

    with Session('LLMJURY'):
        eval_data = Connector('input_jsons')

        # Add all data to connector
        for filename, json_file in eval_json_result_dataset.items():
            for section_id, section_data in json_file.items():
                eval_data.add_data(section_data, section_id=section_id, filename=filename)
        eval_data.finished()

        # Execute evaluation
        evaluation_output = LLMJuryEvaluator(
            eval_data=eval_data,
            criteria_to_be_evaluated=criteria_to_be_evaluated,
            model_list=model_list,
            calc_avg_and_std=calc_avg_and_std,
            logger=logger,
            prompt_config_path=prompt_config_path,
            result_type=result_type,
            custom_prompt_template=custom_prompt_template,
            evaluation_mode=evaluation_mode,
        ).run()

        # 1. Collect results
        for result in evaluation_output.reader():
            evaluation_data = result.read_json()
            if isinstance(evaluation_data, list):
                results.extend(evaluation_data)
            elif isinstance(evaluation_data, dict):
                results.append(evaluation_data)

        if not results:
            raise ValueError('No results generated')

        # 2. Save raw JSON results first (safety measure)
        logger.info(f'💾 Saving JSON results to: {output_folder}')
        add_dict_as_json_file(data=results, filename=output_name, folder_path=output_folder)

        # 3. Transform results to DataFrame
        logger.info('🔄 Transforming results to DataFrame...')
        transformer = LLMJuryResultsTransformer(results=results, evaluation_mode=evaluation_mode, logger=logger)
        transformed_result = transformer.run()
        merged_df = transformed_result.get('transformed')

        # 4. Generate all report sheets
        logger.info('📊 Generating report sheets...')
        report_generator = LLMJuryReportGenerator(df_pivot=merged_df, logger=logger)
        all_sheets = report_generator.run()

        # 5. (Optional) Generate executive summary via meta-analysis
        if (
            enable_meta_analysis
            and evaluation_mode == EvaluationMode.METRICS
            and model_list
            and isinstance(merged_df, pd.DataFrame)
            and not merged_df.empty
        ):
            try:
                logger.info('🔍 Running meta-analysis for executive summary...')
                meta_analyzer = LLMJuryMetaAnalyzer(
                    df=merged_df,
                    model=model_list[0],  # Use first model for meta-analysis
                    logger=logger,
                    score_threshold=meta_score_threshold,
                    prompt_config=meta_prompt_config,
                    custom_prompt_template=meta_custom_prompt,
                )
                exec_summary_df = meta_analyzer.run()
                all_sheets[SheetName.EXECUTIVE_SUMMARY.value] = exec_summary_df
                logger.info('✅ Executive summary generated successfully')
            except Exception as e:
                logger.warning(f'⚠️ Meta-analysis failed (non-critical): {e}')
                # Continue without executive summary - not a critical failure

        # 6. Save Excel with formatting
        logger.info(f'✨ Applying Excel formatting and saving to: {output_folder}')
        persister = LLMJuryExcelPersister(
            dfs=all_sheets, filename=output_name, folder_path=output_folder, logger=logger
        )
        persister.run()

    logger.info(f'✅ Evaluation complete! Results saved as: {output_name}')


def parse_arguments() -> EvaluationConfig:
    """Parse CLI arguments and return evaluation configuration."""
    parser = argparse.ArgumentParser(
        description='Run LLM Multi-Mode Evaluation', formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--eval_json_path', type=str, required=True, help='Path to the evaluation JSON files')
    parser.add_argument(
        '--criteria',
        type=str,
        nargs='*',
        default=None,
        choices=[criteria.value for criteria in EvaluationCriteria],
        help='Criteria to evaluate. If not specified, uses summary evaluation default (choices: %(choices)s)',
    )
    parser.add_argument(
        '--models',
        type=str,
        nargs='*',
        default=None,
        help='List of models to use (case-insensitive). If not specified, uses [gpt_4o_mini, gpt_5_mini]',
    )
    parser.add_argument('--name', type=str, default='', help='Suffix to add to output files')
    parser.add_argument(
        '--calc_avg_and_std',
        action='store_true',
        default=True,
        help='Whether to calculate average and standard deviation',
    )
    parser.add_argument('--prompt_config_path', type=str, default=None, help='Path to prompt version config file')
    parser.add_argument('--result_type', type=str, default=None, help='Optional result type for evaluation')
    parser.add_argument('--custom_prompt_template', type=str, default=None, help='Optional custom prompt template')
    parser.add_argument(
        '--evaluation_mode',
        type=str,
        default='metrics',
        choices=[mode.value for mode in EvaluationMode],
        help='Evaluation mode (metrics, question_answer, or comparison).',
    )
    parser.add_argument(
        '--enable_meta_analysis',
        action='store_true',
        help='Generate executive summary via meta-analysis (METRICS mode only)',
    )
    parser.add_argument(
        '--meta_score_threshold',
        type=float,
        default=3.5,
        help='Score threshold for meta-analysis concerning files (default: 3.5)',
    )
    parser.add_argument(
        '--meta_prompt_config',
        type=str,
        default=None,
        help='Prompt config for meta-analysis (e.g., meta_analysis_v1)',
    )
    parser.add_argument(
        '--meta_custom_prompt',
        type=str,
        default=None,
        help='Custom prompt template for meta-analysis',
    )
    args = parser.parse_args()

    return EvaluationConfig(
        eval_json_path=Path(args.eval_json_path),
        criteria=args.criteria,
        models=args.models,
        name=args.name,
        calc_avg_and_std=args.calc_avg_and_std,
        prompt_config_path=args.prompt_config_path,
        result_type=args.result_type,
        custom_prompt_template=args.custom_prompt_template,
        evaluation_mode=EvaluationMode(args.evaluation_mode),
        enable_meta_analysis=args.enable_meta_analysis,
        meta_score_threshold=args.meta_score_threshold,
        meta_prompt_config=args.meta_prompt_config,
        meta_custom_prompt=args.meta_custom_prompt,
    )


if __name__ == '__main__':
    """
    LLM Multi-Mode Evaluation Runner.

    Usage:
        # Basic evaluation
        python runners/run_llmjury_evaluator.py --eval_json_path /path/to/json \\
            --evaluation_mode metrics \\
            --criteria accuracy comprehensiveness \\
            --models gpt_4o_mini gemini-2.5-flash \\
            --name my_eval

        # With executive summary (meta-analysis)
        python runners/run_llmjury_evaluator.py --eval_json_path /path/to/json \\
            --evaluation_mode metrics \\
            --enable_meta_analysis \\
            --meta_score_threshold 3.5

    Defaults:
        • Criteria: [accuracy, comprehensiveness, conciseness, duplicacy, fluency, navigation, truthfulness]
        • Models: [gpt_4o_mini, gpt_5_mini]
        • Evaluation Mode: metrics
        • Meta-analysis: disabled (use --enable_meta_analysis to enable)
        • Meta-threshold: 3.0

    Evaluation Modes:
        • metrics: Multi-criteria evaluation (accuracy, comprehensiveness, etc.)
        • question_answer: Q&A evaluation with or without source context
        • comparison: Compare two responses or evaluate against ground truth

    Meta-Analysis:
        When --enable_meta_analysis is set (METRICS mode only), generates an executive
        summary sheet analyzing all evaluation results, identifying concerning files,
        quality patterns, and providing actionable recommendations.
    """
    config = parse_arguments()

    # Run evaluation
    llm_evaluator(
        eval_json_path=config.eval_json_path,
        criteria_to_be_evaluated=config.criteria if config.criteria else None,
        models=config.models if config.models else None,
        name=config.name,
        calc_avg_and_std=config.calc_avg_and_std,
        prompt_config_path=config.prompt_config_path,
        result_type=config.result_type,
        custom_prompt_template=config.custom_prompt_template,
        evaluation_mode=config.evaluation_mode,
        enable_meta_analysis=config.enable_meta_analysis,
        meta_score_threshold=config.meta_score_threshold,
        meta_prompt_config=config.meta_prompt_config,
        meta_custom_prompt=config.meta_custom_prompt,
    )

    # ========================================
    # Direct Script Execution (for testing)
    # ========================================
    # Uncomment and modify this section to run without CLI arguments
    """
    # Configuration
    eval_json_path = Path('/path/to/your/evaluation_data.json')
    name = 'my_test_run'

    # Option 1: Basic evaluation
    llm_evaluator(
        eval_json_path=eval_json_path,
        name=name,
    )

    # Option 2: With meta-analysis and custom threshold
    llm_evaluator(
        eval_json_path=eval_json_path,
        name=name,
        enable_meta_analysis=True,
        meta_score_threshold=3.5,
    )

    # Option 3: Custom criteria and models with meta-analysis
    criteria_to_be_evaluated = ['accuracy', 'comprehensiveness', 'conciseness']
    models = [
        'gpt_4o_mini',
        'gpt_5_mini',
        'gemini-2.5-flash',  # Azure deployment example
    ]
    llm_evaluator(
        eval_json_path=eval_json_path,
        criteria_to_be_evaluated=criteria_to_be_evaluated,
        models=models,
        name=name,
        calc_avg_and_std=True,
        evaluation_mode=EvaluationMode.METRICS,
        enable_meta_analysis=True,
        meta_score_threshold=3.5,
        # prompt_config_path='/path/to/prompt_config.json',  # Optional
        # result_type='custom',                               # Optional
        # custom_prompt_template='Custom {criteria_name}',    # Optional
    )
    """
