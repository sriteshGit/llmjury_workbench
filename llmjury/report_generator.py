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
Report Generator Operator for LLM Jury evaluation.

This operator generates summary reports, jury-specific views, and info sheets
from evaluation results DataFrames.
"""

import logging
from typing import Any

import pandas as pd
from llmjury.runtime.operator import Operator

from llmjury.constants import (
    COMPRESSION_RATIO_COL,
    JURY_MODEL,
    OVERALL_REASONING,
    OVERALL_SCORE,
    PERCENTAGE_THRESHOLD,
    SCORE_THRESHOLD,
    SheetName,
)

# Report Summary Column Names (used only in this module)
COL_METRIC = 'Metric'
COL_TOTAL_NON_BLANK_SOURCES = 'Total Non-Blank Sources'
COL_AVERAGE_SCORE = 'Average Score'
COL_MEDIAN_SCORE = 'Median Score'
COL_STANDARD_DEVIATION = 'Standard Deviation'

# Report Summary Column Name Templates (dynamic - require threshold value)
COL_SOURCES_ABOVE_THRESHOLD = 'Sources with >{threshold} Score'
COL_PERCENTAGE_SOURCES_ABOVE_THRESHOLD = 'Percentage of Sources >{threshold} Score'


class LLMJuryReportGenerator(Operator):
    """
    Generate comprehensive reports from LLM Jury evaluation results.

    This operator creates:
    - Summary report with statistics across all metrics
    - Jury-specific results sheet
    - Info sheet with evaluation metadata
    """

    VERSION = '0.1.0'

    def __init__(
        self,
        df_pivot: pd.DataFrame,
        logger: logging.Logger | None = None,
        score_threshold: float | None = None,
        percentage_threshold: int | None = None,
    ):
        """
        Initialize report generator.

        Args
        ----
            df_pivot: DataFrame containing evaluation results (merged data)
            logger: Optional logger instance
            score_threshold: Optional score threshold (defaults to constant if not provided)
            percentage_threshold: Optional percentage threshold (defaults to constant if not provided)
        """
        super().__init__()
        self.df_pivot = df_pivot
        self.logger = logger or logging.getLogger(__name__)
        self.score_threshold = score_threshold if score_threshold is not None else SCORE_THRESHOLD
        self.percentage_threshold = percentage_threshold if percentage_threshold is not None else PERCENTAGE_THRESHOLD

    def _find_columns_containing(self, text: str) -> list[str]:
        """Find columns containing specific text."""
        return [col for col in self.df_pivot.columns if text in col]

    def _get_jury_columns(self) -> tuple[list[str], list[str]]:
        """
        Get Jury score and reasoning columns for all modes.

        Returns
        -------
            Tuple of (jury_score_cols, jury_reasoning_cols)
        """
        # All modes use lowercase pattern: '{prefix}_score_Jury', '{prefix}_reasoning_Jury'
        jury_score_cols = self._find_columns_containing(f'_score_{JURY_MODEL}')
        jury_reasoning_cols = self._find_columns_containing(f'_reasoning_{JURY_MODEL}')
        return jury_score_cols, jury_reasoning_cols

    def run(self) -> dict[str, pd.DataFrame]:
        """
        Generate all sheets (add new sheets here when extending SheetName enum).

        Returns
        -------
            Dictionary mapping sheet names to DataFrames
        """
        return {
            SheetName.MERGED.value: self.df_pivot,
            SheetName.REPORT.value: self.create_summary_report(),
            SheetName.JURY_RESULTS.value: self.create_jury_results_sheet(),
            SheetName.INFO.value: self.create_info_sheet(),
        }

    def create_summary_report(self) -> pd.DataFrame:
        """
        Create a summary report from the evaluation results.

        Returns
        -------
            DataFrame containing summary statistics for each metric
        """
        if self.df_pivot.empty:
            self.logger.warning('Empty DataFrame provided for report creation')
            return pd.DataFrame()

        try:
            # Get Jury columns using helper method
            jury_score_columns, _ = self._get_jury_columns()

            # If no Jury columns found, look for any score columns as fallback
            if not jury_score_columns:
                jury_score_columns = self._find_columns_containing('_score')

            calculated_score_columns = self._find_columns_containing('calculated_score')
            overall_score_columns = self._find_columns_containing(OVERALL_SCORE)

            # Combine all score columns
            all_score_columns = jury_score_columns + calculated_score_columns + overall_score_columns

            if not all_score_columns:
                self.logger.warning('No score columns found in DataFrame')
                return pd.DataFrame()

            summary_data: dict[str, Any] = {
                COL_METRIC: [],
                COL_TOTAL_NON_BLANK_SOURCES: [],
                COL_SOURCES_ABOVE_THRESHOLD.format(threshold=self.score_threshold): [],
                COL_PERCENTAGE_SOURCES_ABOVE_THRESHOLD.format(threshold=self.score_threshold): [],
                COL_AVERAGE_SCORE: [],
                COL_MEDIAN_SCORE: [],
                COL_STANDARD_DEVIATION: [],
            }

            for column in all_score_columns:
                # Calculate basic statistics
                scores = self.df_pivot[column].dropna()
                total_non_blank = len(scores)

                if total_non_blank == 0:
                    continue

                greater_than_threshold = (scores > self.score_threshold).sum()
                percentage = (greater_than_threshold / total_non_blank) * 100

                # Calculate additional statistics
                avg_score = scores.mean()
                median_score = scores.median()
                std_dev = scores.std()

                summary_data[COL_METRIC].append(column)
                summary_data[COL_TOTAL_NON_BLANK_SOURCES].append(total_non_blank)
                summary_data[COL_SOURCES_ABOVE_THRESHOLD.format(threshold=self.score_threshold)].append(
                    greater_than_threshold
                )
                summary_data[COL_PERCENTAGE_SOURCES_ABOVE_THRESHOLD.format(threshold=self.score_threshold)].append(
                    percentage
                )
                summary_data[COL_AVERAGE_SCORE].append(avg_score)
                summary_data[COL_MEDIAN_SCORE].append(median_score)
                summary_data[COL_STANDARD_DEVIATION].append(std_dev)

            if not summary_data[COL_METRIC]:
                self.logger.warning('No valid metrics found for report')
                return pd.DataFrame()

            # Create summary DataFrame
            summary_df = pd.DataFrame(summary_data)

            # Format percentage column
            percentage_col = COL_PERCENTAGE_SOURCES_ABOVE_THRESHOLD.format(threshold=self.score_threshold)
            summary_df[percentage_col] = summary_df[percentage_col].round(2)

            # Format numeric columns
            numeric_columns = [COL_AVERAGE_SCORE, COL_MEDIAN_SCORE, COL_STANDARD_DEVIATION]
            for col in numeric_columns:
                summary_df[col] = summary_df[col].round(2)

            return summary_df

        except Exception as e:
            self.logger.error(f'Error creating report: {e}')
            return pd.DataFrame()

    def create_jury_results_sheet(self) -> pd.DataFrame:
        """
        Create a sheet containing Jury scores, reasoning, and overall scores.

        Returns
        -------
            DataFrame containing Jury results
        """
        if self.df_pivot.empty:
            self.logger.warning('Empty DataFrame provided for jury results creation')
            return pd.DataFrame()

        try:
            # Get Jury columns using helper method
            jury_score_cols, jury_reasoning_cols = self._get_jury_columns()

            # Get overall score and reasoning columns (used in multi-criteria METRICS mode)
            overall_cols = self._find_columns_containing(OVERALL_SCORE) + self._find_columns_containing(
                OVERALL_REASONING
            )

            # Get content columns (source, response, etc.)
            content_cols = []
            for col in ['source', 'response', 'response_a', 'response_b', 'question']:
                if col in self.df_pivot.columns:
                    content_cols.append(col)

            # Get word count and compression columns that exist in the DataFrame
            word_count_cols = self._find_columns_containing('_word_count')
            compression_cols = self._find_columns_containing(COMPRESSION_RATIO_COL)

            # Combine all columns we want to keep
            index_columns = ['filename', 'section_id']
            columns_to_keep = (
                index_columns
                + content_cols
                + word_count_cols
                + compression_cols
                + jury_score_cols
                + jury_reasoning_cols
                + overall_cols
            )

            # Filter to only include columns that exist
            columns_to_keep = [col for col in columns_to_keep if col in self.df_pivot.columns]

            # Need either Jury columns or overall columns to create this sheet
            has_jury_cols = bool(jury_score_cols or jury_reasoning_cols)
            has_overall_cols = bool(overall_cols)

            if len(columns_to_keep) <= len(index_columns) or not (has_jury_cols or has_overall_cols):
                self.logger.warning('No Jury or overall columns found for jury results sheet')
                return pd.DataFrame()

            # Create jury results DataFrame
            jury_df = self.df_pivot[columns_to_keep].copy()

            # Rename columns to remove Jury suffix for cleaner display
            # Handle both uppercase and lowercase patterns
            column_mapping = {}
            for col in jury_score_cols + jury_reasoning_cols:
                if col in jury_df.columns:
                    # Remove _Jury suffix (handles both _Score_Jury and _score_Jury)
                    new_name = col.replace(f'_{JURY_MODEL}', '')
                    column_mapping[col] = new_name

            if column_mapping:
                jury_df = jury_df.rename(columns=column_mapping)

            return jury_df

        except Exception as e:
            self.logger.error(f'Error creating jury results sheet: {e}')
            return pd.DataFrame()

    def create_info_sheet(self) -> pd.DataFrame:
        """
        Create an info sheet with evaluation system documentation.

        Returns
        -------
            DataFrame containing the info information
        """
        # Data-driven info structure: (Category, Metric, Value, Description)
        info_data = [
            # Excel Sheet Structure
            (
                'Excel Sheets',
                '1. Merged Results',
                'Complete Dataset',
                'All evaluation data: filename, section_id, source text, response, scores, reasoning, word counts',
            ),
            (
                'Excel Sheets',
                '2. Report',
                'Aggregated Stats',
                'Per-metric statistics: total sources, sources above threshold, averages, medians, std deviations',
            ),
            (
                'Excel Sheets',
                '3. Jury Results',
                'Jury Evaluations',
                'Filtered view with only jury model scores and reasoning (cleaner view for jury-specific analysis)',
            ),
            (
                'Excel Sheets',
                '4. Info Sheet',
                'Documentation',
                'This sheet - comprehensive guide to system configuration, thresholds, and column mappings',
            ),
            # Score Thresholds
            (
                'Thresholds',
                'Score Threshold',
                f'{self.score_threshold}',
                'Minimum acceptable score (1-5 scale). Scores below this are highlighted red',
            ),
            (
                'Thresholds',
                'Percentage Threshold',
                f'{self.percentage_threshold}%',
                'Minimum acceptable % of sources above score threshold',
            ),
            ('Thresholds', 'Score Range', '1.0 - 5.0', 'All scores are on a 5-point scale (1=poor, 5=excellent)'),
            # Color Coding
            (
                'Excel Formatting',
                'Red Fill',
                f'Score < {self.score_threshold}',
                'Scores below threshold - indicates areas needing improvement',
            ),
            (
                'Excel Formatting',
                'Green Fill',
                f'Score ≥ {self.score_threshold}',
                'Scores meeting/exceeding threshold - indicates good performance',
            ),
            (
                'Excel Formatting',
                'Compression Tiers',
                '5-Level Color Scale',
                'Compression ratio colors: <5% (red), 5-7.5% (misty rose), 7.5-10% (lavender), '
                '10-15% (honeydew), >15% (red - too compressed)',
            ),
            ('Excel Formatting', 'Bold Headers', 'First Row', 'All sheet headers are bold and centered for clarity'),
            (
                'Excel Formatting',
                'Auto-Width Columns',
                'Dynamic',
                'Column widths auto-adjusted based on content (max 50 chars)',
            ),
            # Evaluation Modes
            (
                'Evaluation Modes',
                'METRICS',
                'Multi-Criteria',
                'Evaluate response against source using multiple criteria (accuracy, comprehensiveness, etc.)',
            ),
            (
                'Evaluation Modes',
                'QUESTION_ANSWER',
                'Q&A Evaluation',
                'Evaluate answer quality with or without source context',
            ),
            (
                'Evaluation Modes',
                'COMPARISON',
                'Compare Texts',
                'Compare two responses OR evaluate response against ground truth',
            ),
            # Column Structure
            (
                'Column Structure',
                'Identity Columns',
                'filename, section_id',
                'Unique identifiers for each evaluated source (always present in merged sheet)',
            ),
            (
                'Column Structure',
                'Score Columns',
                '{metric}_score_{model}',
                'Pattern: accuracy_score_jury, comprehensiveness_score_jury (one per metric per model)',
            ),
            (
                'Column Structure',
                'Reasoning Columns',
                '{metric}_reasoning_{model}',
                'Pattern: accuracy_reasoning_jury (LLM explanation for each score)',
            ),
            (
                'Column Structure',
                'Prompt Version Columns',
                '{metric}_prompt_version_{model}',
                'Tracks which prompt version was used for each evaluation',
            ),
            # Normalized Column Names
            (
                'Normalized Columns',
                'source',
                '→ source_word_count',
                'Reference/context text used for evaluation (all modes)',
            ),
            (
                'Normalized Columns',
                'response',
                '→ response_word_count',
                'Output/answer being evaluated (METRICS and Q&A modes)',
            ),
            (
                'Normalized Columns',
                'response_a',
                '→ response_a_word_count',
                'First response in comparison (COMPARISON mode)',
            ),
            (
                'Normalized Columns',
                'response_b',
                '→ response_b_word_count',
                'Second response in comparison (COMPARISON mode)',
            ),
            (
                'Normalized Columns',
                'compression_ratio_percentage',
                'Auto-calculated',
                'Response length as % of source (METRICS mode only)',
            ),
            # Input Field Mappings (automatically recognized)
            (
                'Input Fields',
                'Source/Reference',
                'prompt, section_text, context, ground_truth',
                'Any of these field names → normalized to "source"',
            ),
            (
                'Input Fields',
                'Response/Output',
                'summary, answer, response, output',
                'Any of these field names → normalized to "response"',
            ),
            (
                'Input Fields',
                'First Response',
                'summary1, response1, option_a, output1',
                'Any of these field names → normalized to "response_a"',
            ),
            (
                'Input Fields',
                'Second Response',
                'summary2, response2, option_b, output2',
                'Any of these field names → normalized to "response_b"',
            ),
            ('Input Fields', 'Question', 'question, query, prompt_text', 'Question field for Q&A mode (kept as-is)'),
            # Model Support
            (
                'Model Support',
                'Factory Models',
                'gpt_4o_mini, etc.',
                'Pre-configured models from llms module (lowercase names)',
            ),
            (
                'Model Support',
                'Azure Deployments',
                'deployment-name',
                'Custom Azure deployment names (e.g., gemini-2.5-pro)',
            ),
            (
                'Model Support',
                'Supported Families',
                'GPT, Claude, Gemini, AWS Nova',
                'Automatic detection of model family from deployment name',
            ),
            (
                'Model Support',
                'Jury Model',
                'jury',
                'Aggregated verdict from multiple models (if using multiple models)',
            ),
            # Word Count & Calculations
            ('Calculations', 'Word Count Method', 'text.split()', 'Simple and fast - splits on whitespace'),
            (
                'Calculations',
                'Compression Ratio',
                '(response_words / source_words) × 100',
                'Percentage of original length (METRICS mode only)',
            ),
            (
                'Calculations',
                'Calculated Score',
                'Average after outlier removal',
                'Jury score computed from multiple model scores',
            ),
            ('Calculations', 'Standard Deviation', 'Score consistency', 'Lower = more agreement between models'),
            # Output & Results
            ('Output', 'Excel File', 'Multiple sheets', 'Formatted Excel with merged, report, jury, and info sheets'),
            (
                'Output',
                'JSON Files',
                'Raw evaluation data',
                'Complete evaluation results in JSON format (if configured)',
            ),
            (
                'Output',
                'Normalized Data',
                'Consistent columns',
                'All field names normalized for consistent analysis across datasets',
            ),
            # Usage Guide
            (
                'How to Use',
                'Quick Analysis',
                'Start with Report sheet',
                'View summary statistics to identify metrics with low scores or high percentages below threshold',
            ),
            (
                'How to Use',
                'Deep Dive',
                'Use Merged sheet',
                'Sort/filter by specific scores, search reasoning text, analyze individual sources in detail',
            ),
            (
                'How to Use',
                'Jury Focus',
                'Check Jury Results sheet',
                'Clean view of jury evaluations without other model columns (useful for presentations)',
            ),
            (
                'How to Use',
                'Understand Config',
                'Reference Info sheet',
                'This sheet explains all settings, thresholds, column patterns, and field mappings',
            ),
            (
                'How to Use',
                'Identify Issues',
                'Look for red cells',
                'Red-highlighted scores indicate performance below threshold - focus improvement efforts here',
            ),
        ]

        # Convert to DataFrame
        df = pd.DataFrame(info_data, columns=['Category', 'Metric', 'Value', 'Description'])
        return df
