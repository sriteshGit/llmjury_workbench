#!/usr/bin/env python3
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
Transform LLM Jury Results from JSON to Excel.

This script loads evaluation results from a JSON file and runs the transformation
pipeline (step 3 onwards from run_llmjury_evaluator.py).

Usage:
    python transform_llmjury_results.py --json_path /path/to/results.json --output_dir /path/to/output

    # Minimal output (recommended for automation)
    python transform_llmjury_results.py --json_path results.json --output_dir . --quiet

Examples:
    # Basic usage
    python transform_llmjury_results.py --json_path data.json --output_dir output/

    # With custom output name
    python transform_llmjury_results.py --json_path data.json --output_name my_analysis

    # Specify evaluation mode explicitly
    python transform_llmjury_results.py --json_path data.json --evaluation_mode metrics
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from llmjury.env_bootstrap import load_llmjury_env

load_llmjury_env()

import pandas as pd

from llmjury.constants import EvaluationMode
from llmjury.runtime.session import Session
from llmjury.excel_persister import LLMJuryExcelPersister
from llmjury.llm_jury_results_transformer import LLMJuryResultsTransformer
from llmjury.report_generator import LLMJuryReportGenerator

# Logger instance (level set by CLI argument)
logger = logging.getLogger(__name__)


def load_json_results(json_path: Path) -> list[dict[str, Any]]:
    """
    Load evaluation results from JSON file.

    Args:
        json_path: Path to the JSON file

    Returns:
        List of evaluation result dictionaries

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
        ValueError: If JSON format is unexpected
    """
    if not json_path.exists():
        raise FileNotFoundError(f'JSON file not found: {json_path}')

    logger.info(f'Loading JSON from: {json_path}')

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    # Handle both list and dict formats
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        # Extract results from eval_json_result_dataset format
        results = []
        for value in data.values():
            if isinstance(value, list):
                results.extend(value)
            elif isinstance(value, dict):
                results.append(value)
    else:
        raise ValueError(f'Unexpected JSON format: {type(data).__name__}')

    if not results:
        raise ValueError('No evaluation records found in JSON file')

    logger.info(f'Loaded {len(results)} records')
    return results


def detect_evaluation_mode(results: list[dict[str, Any]]) -> EvaluationMode:
    """
    Auto-detect the evaluation mode from the results structure.

    Args:
        results: List of evaluation results

    Returns:
        Detected EvaluationMode

    Detection Logic:
        - COMPARISON: If 'response_a' or 'response_b' present
        - QUESTION_ANSWER: If both 'question' and 'answer' present
        - METRICS: Default mode (summary evaluation)
    """
    if not results:
        logger.warning('Empty results provided, defaulting to METRICS mode')
        return EvaluationMode.METRICS

    first_record = results[0]

    # Check for comparison mode indicators
    if 'response_a' in first_record or 'response_b' in first_record:
        logger.info('Detected mode: COMPARISON')
        return EvaluationMode.COMPARISON

    # Check for QA mode indicators
    if 'question' in first_record and 'answer' in first_record:
        logger.info('Detected mode: QUESTION_ANSWER')
        return EvaluationMode.QUESTION_ANSWER

    # Default to metrics mode
    logger.info('Detected mode: METRICS')
    return EvaluationMode.METRICS


def transform_and_save(
    results: list[dict[str, Any]],
    output_dir: Path,
    output_name: str = 'llmjury_transformed',
    evaluation_mode: EvaluationMode | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """
    Transform results and save to Excel and CSV.

    Args:
        results: List of evaluation result dictionaries
        output_dir: Directory to save output files
        output_name: Base name for output files (without extension)
        evaluation_mode: Evaluation mode (auto-detected if None)

    Returns:
        Tuple of (transformed_dataframe, all_report_sheets)

    Raises:
        ValueError: If transformation produces no data
    """
    # Auto-detect mode if not provided
    if evaluation_mode is None:
        evaluation_mode = detect_evaluation_mode(results)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Wrap in Venice Session (required for Operators)
    with Session('LLMJURY_TRANSFORM'):
        # Step 1: Transform results to DataFrame
        logger.info('Transforming results to DataFrame...')
        transformer = LLMJuryResultsTransformer(results=results, evaluation_mode=evaluation_mode, logger=logger)
        transformed_result = transformer.run()
        merged_df = transformed_result.get('transformed')

        if merged_df is None or merged_df.empty:
            raise ValueError('Transformation produced no data')

        logger.info(f'Transformed {len(merged_df)} rows × {len(merged_df.columns)} columns')

        # Step 2: Generate report sheets
        logger.info('Generating report sheets...')
        report_generator = LLMJuryReportGenerator(df_pivot=merged_df, logger=logger)
        all_sheets = report_generator.run()
        logger.info(f'Generated {len(all_sheets)} sheets: {", ".join(all_sheets.keys())}')

        # Step 3: Save Excel with formatting
        logger.info(f'Saving Excel to: {output_dir / output_name}.xlsx')
        persister = LLMJuryExcelPersister(dfs=all_sheets, filename=output_name, folder_path=output_dir, logger=logger)
        persister.run()

        # Step 4: Save CSV for easy inspection
        csv_path = output_dir / f'{output_name}_transformed.csv'
        merged_df.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f'Saved CSV to: {csv_path}')

        # Print summary
        _print_summary(results, merged_df, evaluation_mode, all_sheets, output_dir, output_name)

        return merged_df, all_sheets


def _print_summary(
    results: list[dict[str, Any]],
    merged_df: pd.DataFrame,
    evaluation_mode: EvaluationMode,
    all_sheets: dict[str, pd.DataFrame],
    output_dir: Path,
    output_name: str,
) -> None:
    """Print transformation summary."""
    logger.info('\n' + '=' * 80)
    logger.info('TRANSFORMATION SUMMARY')
    logger.info('=' * 80)
    logger.info(f'Input records:    {len(results)}')
    logger.info(f'Output rows:      {len(merged_df)}')
    logger.info(f'Output columns:   {len(merged_df.columns)}')
    logger.info(f'Evaluation mode:  {evaluation_mode.value}')
    logger.info(f'Report sheets:    {len(all_sheets)} ({", ".join(all_sheets.keys())})')
    logger.info(f'Output directory: {output_dir}')
    logger.info(f'Excel file:       {output_name}.xlsx')
    logger.info(f'CSV file:         {output_name}_transformed.csv')
    logger.info('=' * 80)


def setup_logging(quiet: bool = False) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        quiet: If True, only show warnings and errors
    """
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s' if quiet else '%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()],
        force=True,  # Override any existing configuration
    )


def parse_arguments() -> argparse.Namespace:
    """Parse and validate command line arguments."""
    parser = argparse.ArgumentParser(
        description='Transform LLM Jury evaluation results from JSON to Excel',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--json_path',
        type=str,
        required=True,
        help='Path to the JSON file with evaluation results',
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default='.',
        help='Directory to save output files (Excel and CSV)',
    )
    parser.add_argument(
        '--output_name',
        type=str,
        default='llmjury_transformed',
        help='Base name for output files (without extension)',
    )
    parser.add_argument(
        '--evaluation_mode',
        type=str,
        default=None,
        choices=['metrics', 'question_answer', 'comparison'],
        help='Evaluation mode (auto-detected if not specified)',
    )
    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='Minimal output (only warnings and errors)',
    )

    return parser.parse_args()


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_arguments()

    # Setup logging
    setup_logging(quiet=args.quiet)

    # Convert paths
    json_path = Path(args.json_path).resolve()
    output_dir = Path(args.output_dir).resolve()

    # Convert mode if provided
    evaluation_mode = EvaluationMode(args.evaluation_mode) if args.evaluation_mode else None

    try:
        # Load results
        results = load_json_results(json_path)

        # Transform and save
        transform_and_save(
            results=results,
            output_dir=output_dir,
            output_name=args.output_name,
            evaluation_mode=evaluation_mode,
        )

        logger.info('✓ Transformation completed successfully')
        return 0

    except FileNotFoundError as e:
        logger.error(f'File not found: {e}')
        return 1
    except json.JSONDecodeError as e:
        logger.error(f'Invalid JSON: {e}')
        return 1
    except ValueError as e:
        logger.error(f'Validation error: {e}')
        return 1
    except Exception as e:
        logger.error(f'Unexpected error: {e}', exc_info=not args.quiet)
        return 1


if __name__ == '__main__':
    sys.exit(main())
