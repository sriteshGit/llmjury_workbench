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
Meta Analyzer for LLM Jury Evaluation Results.

Provides both standalone and Operator-based executive summary generation.
Self-contained with no dependencies on report_generator or transformer.
"""

import json
import logging
from pathlib import Path
from typing import Any

import openpyxl  # type: ignore[import-untyped]
import pandas as pd
from langchain_core.prompts import PromptTemplate
from venice.core.Connector import Connector
from venice.core.Operator import Operator
from venice.core.Session import Session
from venice_gentech.common.llm.chat_llm_invoker import ChatLLMInvoker
from venice_gentech.common.llm.llm_wrapper import ModelFactory

from llmjury.constants import SheetName
from llmjury.support.prompt_constants import CONTENT, HUMAN, SYSTEM, TYPE

# Default prompt paths
PROMPTS_BASE_PATH = Path(__file__).parent.parent.parent / 'data' / 'prompts' / 'llmJURY' / 'analysis'
DEFAULT_PROMPT_CONFIG = 'meta_analysis_v1'


def run_standalone_meta_analysis(
    df: pd.DataFrame,
    model: ModelFactory,
    logger: logging.Logger | None = None,
    score_threshold: float = 3.0,
    prompt_config: str | None = None,
    custom_prompt_template: str | None = None,
) -> pd.DataFrame:
    """
    Generate executive summary from jury results.

    Parameters
    ----------
    df : pd.DataFrame
        Transformed jury results DataFrame
    model : ModelFactory
        Model to use for meta-analysis
    logger : logging.Logger, optional
        Logger instance
    score_threshold : float, default=3.0
        Score below which files are considered concerning
    prompt_config : str, optional
        Prompt config name (e.g., 'meta_analysis_v1')
    custom_prompt_template : str, optional
        Custom prompt template string

    Returns
    -------
    pd.DataFrame
        Single-cell DataFrame with executive summary
    """
    logger = logger or logging.getLogger(__name__)

    if df.empty:
        logger.warning('Empty DataFrame - skipping meta-analysis')
        return pd.DataFrame([{'Executive Summary': 'No data available for analysis'}])

    try:
        meta_data = _prepare_data(df, logger)
        if not meta_data:
            return pd.DataFrame([{'Executive Summary': 'No score/reasoning columns found'}])

        logger.info('Generating analysis prompt...')
        prompt_text = _create_prompt(meta_data, score_threshold, prompt_config, custom_prompt_template, logger)

        logger.info('Running LLM meta-analysis...')
        response_text = _invoke_llm(prompt_text, model, logger)

        logger.info('Executive summary generated successfully')
        return pd.DataFrame([{'Executive Summary': str(response_text)}])

    except Exception as e:
        logger.error(f'Meta-analysis failed: {e}', exc_info=True)
        return pd.DataFrame([{'Executive Summary': f'Error: {str(e)}'}])


def save_executive_summary(
    summary_df: pd.DataFrame,
    output_path: Path,
    excel_path: Path | None = None,
    mode: str = 'new_file',
    logger: logging.Logger | None = None,
) -> None:
    """
    Save executive summary to file (text, Excel, or append).

    Parameters
    ----------
    summary_df : pd.DataFrame
        Executive summary DataFrame
    output_path : Path
        Output file path
    excel_path : Path, optional
        Original Excel file (for 'append' mode)
    mode : str
        Save mode: 'new_file', 'append', or 'text'
    logger : logging.Logger, optional
        Logger instance
    """
    logger = logger or logging.getLogger(__name__)

    if mode == 'append' and excel_path:
        _append_to_excel(summary_df, excel_path, logger)
    elif mode == 'text':
        _save_as_text(summary_df, output_path, logger)
    else:
        _save_as_new_excel(summary_df, output_path, logger)


class LLMJuryMetaAnalyzer(Operator):
    """
    Venice Operator for executive summary generation in evaluation pipelines.

    Use this when integrating with run_llmjury_evaluator.py or other pipelines.
    """

    VERSION = '0.1.0'

    def __init__(
        self,
        df: pd.DataFrame,
        model: ModelFactory,
        logger: logging.Logger | None = None,
        score_threshold: float = 3.0,
        prompt_config: str | None = None,
        custom_prompt_template: str | None = None,
    ):
        """Initialize meta analyzer operator."""
        super().__init__()
        self.df = df
        self.model = model
        self.logger = logger or logging.getLogger(__name__)
        self.score_threshold = score_threshold
        self.prompt_config = prompt_config
        self.custom_prompt_template = custom_prompt_template

    def run(self) -> pd.DataFrame:
        """Execute meta-analysis and return DataFrame."""
        if self.df.empty:
            self.logger.warning('Empty DataFrame - skipping meta-analysis')
            return pd.DataFrame([{'Executive Summary': 'No data available'}])

        try:
            self.logger.info('Preparing meta-analysis data...')
            meta_data = _prepare_data(self.df, self.logger)

            if not meta_data:
                return pd.DataFrame([{'Executive Summary': 'No jury results found'}])

            self.logger.info('Generating analysis prompt...')
            prompt_text = _create_prompt(
                meta_data, self.score_threshold, self.prompt_config, self.custom_prompt_template, self.logger
            )

            self.logger.info('Running LLM meta-analysis...')
            response_text = self._invoke_llm_operator(prompt_text)

            self.logger.info('Executive summary generated successfully')
            return pd.DataFrame([{'Executive Summary': str(response_text)}])

        except Exception as e:
            self.logger.error(f'Meta-analysis failed: {e}', exc_info=True)
            return pd.DataFrame([{'Executive Summary': f'Error: {str(e)}'}])

    def _invoke_llm_operator(self, prompt_text: str) -> str:
        """Invoke LLM within Operator context (assumes Session exists)."""
        prompt_messages = [
            {TYPE: SYSTEM, CONTENT: 'You are an expert evaluator analyzing LLM evaluation results.'},
            {TYPE: HUMAN, CONTENT: prompt_text},
        ]

        prompts = Connector('meta_analysis_prompt')
        prompts.write_json(prompt_messages)
        prompts.finished()

        llm_wrapper = self.model.get_llm_wrapper()
        response = ChatLLMInvoker(prompts=prompts, llm_wrapper=llm_wrapper, stream=False, name='MetaAnalyzer').run()

        result = response.all_text()
        return str(result) if not isinstance(result, str) else result


def _prepare_data(df: pd.DataFrame, logger: logging.Logger) -> list[dict[str, Any]]:
    """Extract jury scores and reasoning, exclude full source/response text."""
    # Detect score columns (pivoted or non-pivoted)
    jury_cols = [col for col in df.columns if '_jury' in col.lower()]

    if jury_cols:
        score_cols = [col for col in jury_cols if '_score' in col]
        reasoning_cols = [col for col in jury_cols if '_reasoning' in col]
    else:
        score_cols = [col for col in df.columns if col.endswith('_score') and not col.startswith('overall_')]
        reasoning_cols = [col for col in df.columns if col.endswith('_reasoning') and not col.startswith('overall_')]

    overall_cols = [col for col in df.columns if col.startswith('overall_')]
    essential_cols = ['filename', 'section_id']

    columns_to_extract = essential_cols + score_cols + reasoning_cols + overall_cols
    columns_to_extract = [col for col in columns_to_extract if col in df.columns]

    if len(columns_to_extract) <= len(essential_cols):
        logger.warning('No score/reasoning columns found')
        return []

    logger.info(f'Found {len(score_cols)} score columns and {len(reasoning_cols)} reasoning columns')

    df_subset = df[columns_to_extract].copy()
    records = df_subset.to_dict('records')

    cleaned: list[dict[str, Any]] = []
    for record in records:
        clean_record = {str(k): v for k, v in record.items() if pd.notna(v)}
        if len(clean_record) > 2:
            cleaned.append(clean_record)

    return cleaned


def _load_prompt_template(prompt_config: str | None, logger: logging.Logger) -> str:
    """Load prompt template from config file."""
    config_name = prompt_config or DEFAULT_PROMPT_CONFIG
    config_path = PROMPTS_BASE_PATH / 'configs' / f'{config_name}.json'

    if not config_path.exists():
        logger.warning(f'Prompt config not found: {config_path}, using default')
        config_name = DEFAULT_PROMPT_CONFIG
        config_path = PROMPTS_BASE_PATH / 'configs' / f'{config_name}.json'

    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    version = config['version']
    prompt_id = config['id']
    prompt_text_path = PROMPTS_BASE_PATH / config['prompt_text_path'] / version / f'{prompt_id}.txt'

    if not prompt_text_path.exists():
        raise FileNotFoundError(f'Prompt template not found: {prompt_text_path}')

    with open(prompt_text_path, encoding='utf-8') as f:
        prompt_text = f.read()

    # Remove the wrapping variable assignment if present
    if prompt_text.startswith('META_ANALYSIS_PROMPT = ('):
        prompt_text = prompt_text.replace('META_ANALYSIS_PROMPT = (', '', 1)
        if prompt_text.endswith(')'):
            prompt_text = prompt_text[:-1].strip()

    return prompt_text


def _create_prompt(
    meta_data: list[dict[str, Any]],
    score_threshold: float,
    prompt_config: str | None = None,
    custom_prompt_template: str | None = None,
    logger: logging.Logger | None = None,
) -> str:
    """Generate detailed, structured prompt for executive summary analysis."""
    logger = logger or logging.getLogger(__name__)

    # Prepare file-level analysis and statistics
    file_analysis, aggregated_stats = _prepare_prompt_data(meta_data, score_threshold)

    # Use custom prompt if provided
    if custom_prompt_template:
        logger.info('Using custom prompt template for meta-analysis')
        template = PromptTemplate.from_template(custom_prompt_template)
        return template.format(
            score_threshold=score_threshold,
            file_analysis=file_analysis,
            aggregated_stats=aggregated_stats,
        )

    # Load prompt from file
    logger.info(f'Loading prompt config: {prompt_config or DEFAULT_PROMPT_CONFIG}')
    prompt_template_text = _load_prompt_template(prompt_config, logger)

    # Format the prompt with variables
    template = PromptTemplate.from_template(prompt_template_text)
    return template.format(
        score_threshold=score_threshold,
        file_analysis=file_analysis,
        aggregated_stats=aggregated_stats,
    )


def _prepare_prompt_data(meta_data: list[dict[str, Any]], score_threshold: float) -> tuple[str, str]:
    """Prepare file analysis and aggregated statistics text for prompt."""
    # Group by filename and calculate comprehensive stats
    file_groups: dict[str, list[dict[str, Any]]] = {}
    for record in meta_data:
        filename = record.get('filename', 'unknown')
        if filename not in file_groups:
            file_groups[filename] = []
        file_groups[filename].append(record)

    # Calculate file-level statistics
    file_stats: list[dict[str, Any]] = []
    for filename, records in file_groups.items():
        criteria_scores: dict[str, list[float]] = {}
        total_scores: list[float] = []

        for record in records:
            for key, value in record.items():
                if '_score' in key and isinstance(value, (int, float)):
                    total_scores.append(float(value))
                    criteria = key.replace('_score_jury', '').replace('_score', '').replace('_', ' ').title()
                    if criteria not in criteria_scores:
                        criteria_scores[criteria] = []
                    criteria_scores[criteria].append(float(value))

        if total_scores:
            avg_score = sum(total_scores) / len(total_scores)
            min_score = min(total_scores)
            max_score = max(total_scores)

            # Categorize scores
            critical = [s for s in total_scores if s < 2.0]
            poor = [s for s in total_scores if 2.0 <= s < 3.0]
            concerning = [s for s in total_scores if 3.0 <= s < score_threshold]
            acceptable = [s for s in total_scores if s >= score_threshold]

            # Calculate criteria averages
            criteria_avgs: dict[str, float] = {
                crit: sum(scores) / len(scores) for crit, scores in criteria_scores.items()
            }

            file_stats.append(
                {
                    'filename': filename,
                    'num_sections': len(records),
                    'avg_score': avg_score,
                    'min_score': min_score,
                    'max_score': max_score,
                    'critical_count': len(critical),
                    'poor_count': len(poor),
                    'concerning_count': len(concerning),
                    'acceptable_count': len(acceptable),
                    'criteria_scores': criteria_avgs,
                }
            )

    # Sort by average score (worst first)
    file_stats.sort(key=lambda x: float(x['avg_score']))

    # Build file analysis text
    file_analysis_parts: list[str] = []
    for i, stats in enumerate(file_stats, 1):
        avg = float(stats['avg_score'])
        severity = (
            '🔴 CRITICAL'
            if avg < 2.0
            else ('🟠 POOR' if avg < 3.0 else '🟡 CONCERNING' if avg < score_threshold else '🟢 ACCEPTABLE')
        )

        file_analysis_parts.extend(
            [
                f"### {i}. {stats['filename']} {severity}",
                '**Overall Performance:**',
                f'- Average Score: {avg:.2f} / 5.0',
                f"- Score Range: {float(stats['min_score']):.1f} - {float(stats['max_score']):.1f}",
                f"- Sections Evaluated: {stats['num_sections']}",
                '',
                '**Score Distribution:**',
                f"- ❌ Critical (< 2.0): {stats['critical_count']} sections",
                f"- ⚠️  Poor (2.0-3.0): {stats['poor_count']} sections",
                f"- ⚡ Concerning (3.0-{score_threshold}): {stats['concerning_count']} sections",
                f"- ✓  Acceptable (≥ {score_threshold}): {stats['acceptable_count']} sections",
                '',
            ]
        )

        # Add criteria breakdown
        criteria_dict = stats.get('criteria_scores')
        if criteria_dict and isinstance(criteria_dict, dict):
            file_analysis_parts.append('**Quality Criteria Scores:**')
            for criteria, avg_val in sorted(criteria_dict.items(), key=lambda x: float(x[1])):
                avg_float = float(avg_val)
                status = (
                    '❌'
                    if avg_float < 2.0
                    else '⚠️' if avg_float < 3.0 else '⚡' if avg_float < score_threshold else '✓'
                )
                file_analysis_parts.append(f'  {status} {criteria}: {avg_float:.2f}')
            file_analysis_parts.append('')

        file_analysis_parts.append('─' * 70)
        file_analysis_parts.append('')

    file_analysis = '\n'.join(file_analysis_parts)

    # Build aggregated statistics text
    total_critical = sum(int(f['critical_count']) for f in file_stats if isinstance(f.get('critical_count'), int))
    total_poor = sum(int(f['poor_count']) for f in file_stats if isinstance(f.get('poor_count'), int))
    total_concerning = sum(int(f['concerning_count']) for f in file_stats if isinstance(f.get('concerning_count'), int))
    total_acceptable = sum(int(f['acceptable_count']) for f in file_stats if isinstance(f.get('acceptable_count'), int))
    total_sections = total_critical + total_poor + total_concerning + total_acceptable

    aggregated_stats_parts = [
        f'- Total Files Analyzed: {len(file_stats)}',
        f'- Total Sections: {total_sections}',
        f'- Critical Issues: {total_critical} ({100*total_critical/total_sections if total_sections else 0:.1f}%)',
        f'- Poor Quality: {total_poor} ({100*total_poor/total_sections if total_sections else 0:.1f}%)',
        f'- Concerning: {total_concerning} ({100*total_concerning/total_sections if total_sections else 0:.1f}%)',
        f'- Acceptable: {total_acceptable} ({100*total_acceptable/total_sections if total_sections else 0:.1f}%)',
    ]

    aggregated_stats = '\n'.join(aggregated_stats_parts)

    return file_analysis, aggregated_stats


def _invoke_llm(prompt_text: str, model: ModelFactory, logger: logging.Logger) -> str:
    """Invoke LLM with minimal Session overhead."""
    try:
        prompt_messages = [
            {TYPE: SYSTEM, CONTENT: 'You are an expert evaluator analyzing LLM evaluation results.'},
            {TYPE: HUMAN, CONTENT: prompt_text},
        ]

        # Use Session only for LLM invocation
        with Session(name='StandaloneMetaAnalysis'):
            prompts = Connector('meta_analysis_prompt')
            prompts.write_json(prompt_messages)
            prompts.finished()

            llm_wrapper = model.get_llm_wrapper()
            response = ChatLLMInvoker(
                prompts=prompts,
                llm_wrapper=llm_wrapper,
                stream=False,
                name='MetaAnalyzer',
            ).run()

            result = response.all_text()

        # Process result outside Session
        return str(result) if not isinstance(result, str) else result
    except Exception as e:
        logger.error(f'Error invoking LLM: {e}')
        return f'Error generating summary: {str(e)}'


def _append_to_excel(summary_df: pd.DataFrame, excel_path: Path, logger: logging.Logger) -> None:
    """Append summary to existing Excel file (replace sheet if exists)."""
    try:
        wb = openpyxl.load_workbook(excel_path)
        if SheetName.EXECUTIVE_SUMMARY.value in wb.sheetnames:
            del wb[SheetName.EXECUTIVE_SUMMARY.value]
            logger.info(f'Removed existing {SheetName.EXECUTIVE_SUMMARY.value} sheet')
        wb.save(excel_path)
        wb.close()
    except Exception as e:
        logger.warning(f'Could not remove existing sheet: {e}')

    with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        summary_df.to_excel(writer, sheet_name=SheetName.EXECUTIVE_SUMMARY.value, index=False)

    logger.info(f'✅ Appended executive summary to: {excel_path}')


def _save_as_text(summary_df: pd.DataFrame, output_path: Path, logger: logging.Logger) -> None:
    """Save summary as text file."""
    summary_text = str(summary_df.iloc[0, 0])
    output_path.write_text(summary_text, encoding='utf-8')
    logger.info(f'✅ Saved executive summary to: {output_path}')


def _save_as_new_excel(summary_df: pd.DataFrame, output_path: Path, logger: logging.Logger) -> None:
    """Save summary as new Excel file."""
    summary_df.to_excel(output_path, sheet_name='Executive Summary', index=False)
    logger.info(f'✅ Saved executive summary to: {output_path}')
