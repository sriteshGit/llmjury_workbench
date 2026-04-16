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
LLM Jury Results Transformer Operator.

This operator transforms raw evaluation results from LLMJuryEvaluator into
structured DataFrames with word counts, compression ratios, and intelligent
column ordering based on evaluation mode.
"""

import json
import logging
from typing import Any

import pandas as pd
from venice.core.Operator import Operator

from llmjury.constants import EvaluationMode
from llmjury.mode_config import get_mode_config


class LLMJuryResultsTransformer(Operator):
    """
    Transform raw evaluation results into structured DataFrames.

    Handles: flattening, word counts, compression ratios, pivoting, column ordering.
    Uses normalized field names (source, response, response_a, response_b).
    """

    VERSION = '0.1.0'

    def __init__(
        self, results: list[dict[str, Any]], evaluation_mode: EvaluationMode, logger: logging.Logger | None = None
    ):
        """Initialize transformer with results and evaluation mode."""
        super().__init__()
        self.results = results
        self.evaluation_mode = evaluation_mode
        self.logger = logger or logging.getLogger(__name__)

    def run(self) -> dict[str, pd.DataFrame]:
        """Transform results into structured DataFrame with word counts and compression ratios."""
        if not self.results:
            self.logger.warning('No results provided to transform')
            return {'transformed': pd.DataFrame()}

        try:
            # Flatten results to handle nested structures
            flat_data = self._flatten_results()
            if not flat_data:
                self.logger.warning('No valid data found in results')
                return {'transformed': pd.DataFrame()}

            # Convert to DataFrame
            df = pd.DataFrame(flat_data)

            # Apply dynamic word count generation
            df = self._generate_word_counts(df)

            # Calculate compression ratio for metrics mode
            df = self._calculate_compression_ratio(df)

            # Get dynamic index columns
            index_columns = self._get_dynamic_index_columns(df.columns.tolist())

            # Ensure required columns exist
            pivot_column = 'model'
            for col in index_columns + [pivot_column]:
                if col not in df.columns:
                    df[col] = None

            # Identify metadata columns
            meta_columns = self._get_metadata_columns(df.columns.tolist())

            # Pivot DataFrame if needed
            df_pivot = self._pivot_dataframe(df, index_columns, pivot_column, meta_columns)

            # Add calculated score columns
            df_pivot = self._add_calculated_scores(df_pivot, df, index_columns)

            # Apply comprehensive column ordering
            df_pivot = self._order_columns(df_pivot, index_columns)

            return {'transformed': df_pivot}

        except Exception as e:
            self.logger.error(f'Error transforming output: {e}')
            # Return a minimal DataFrame with basic structure
            return {'transformed': pd.DataFrame(self.results)}

    def _flatten_results(self) -> list[dict[str, Any]]:
        """Flatten nested result structures."""
        flat_data = []
        for item in self.results:
            if isinstance(item, dict):
                flat_data.append(item)
            elif isinstance(item, list):
                flat_data.extend(item)
        return flat_data

    @staticmethod
    def _word_count(val: Any) -> int | None:
        """Calculate word count for a value."""
        if pd.isna(val):
            return None
        try:
            return len(str(val).split())
        except Exception:
            return None

    @staticmethod
    def _is_jury_model(model_name: str) -> bool:
        """Check if model name is a Jury variant."""
        if pd.isna(model_name):
            return False
        return str(model_name).lower().startswith('jury')

    def _generate_word_counts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate word count columns (auto-adds '_word_count' suffix)."""
        mode_config = get_mode_config(self.evaluation_mode)

        for field in mode_config.word_count_fields:
            if field in df.columns:
                df[f'{field}_word_count'] = df[field].apply(self._word_count)

        return df

    def _calculate_compression_ratio(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate compression ratio for METRICS mode."""
        mode_config = get_mode_config(self.evaluation_mode)
        source_col, response_col, compression_col = (
            'source_word_count',
            'response_word_count',
            'compression_ratio_percentage',
        )

        if mode_config.needs_compression and source_col in df.columns and response_col in df.columns:
            # Ensure word count columns are numeric
            df[source_col] = pd.to_numeric(df[source_col], errors='coerce')
            df[response_col] = pd.to_numeric(df[response_col], errors='coerce')

            # Calculate compression ratio
            compression_series = df.apply(  # type: ignore[call-overload]
                lambda x: (
                    (x[response_col] / x[source_col]) * 100
                    if pd.notna(x[source_col]) and pd.notna(x[response_col]) and x[source_col] > 0
                    else None
                ),
                axis=1,
            )

            # Convert to numeric and round (handles None values gracefully)
            df[compression_col] = pd.to_numeric(compression_series, errors='coerce').round(2)

        return df

    def _get_dynamic_index_columns(self, df_columns: list[str]) -> list[str]:
        """Get index columns from mode configuration (only those present in DataFrame)."""
        mode_config = get_mode_config(self.evaluation_mode)
        existing = [col for col in mode_config.index_columns if col in df_columns]
        return ['filename', 'section_id'] + existing

    def _get_metadata_columns(self, df_columns: list[str]) -> list[str]:
        """Identify metadata columns (not pivoted per model)."""
        text_fields = {'source', 'response', 'response_a', 'response_b', 'question'}

        return [
            col for col in df_columns if col.endswith('_definition') or col.startswith('overall_') or col in text_fields
        ]

    def _handle_duplicate_models(self, df: pd.DataFrame, pivot_column: str, index_columns: list[str]) -> pd.DataFrame:
        """
        Handle duplicate model names by adding unique suffixes.

        Args
        ----
            df: DataFrame with potential duplicate model names
            pivot_column: Column containing model names (usually 'model')
            index_columns: Columns used as index for grouping

        Returns
        -------
            DataFrame with unique model names (duplicates get _run1, _run2, etc. suffixes)

        """
        # Create a copy to avoid modifying original
        df = df.copy()

        # Group by index columns and check for duplicate models within each group
        duplicates_found = False

        for _idx_values, group in df.groupby(index_columns):
            model_counts = group[pivot_column].value_counts()
            duplicate_models = model_counts[model_counts > 1].index.tolist()

            if duplicate_models:
                duplicates_found = True
                # For each duplicate model, add run number suffix
                for dup_model in duplicate_models:
                    dup_indices = group[group[pivot_column] == dup_model].index
                    for run_num, idx in enumerate(dup_indices, start=1):
                        df.loc[idx, pivot_column] = f'{dup_model}_run{run_num}'

        if duplicates_found:
            self.logger.warning(
                'Duplicate model names detected. Added run suffixes (e.g., model_run1, model_run2) '
                'to make them unique for pivoting.'
            )

        return df

    def _pivot_dataframe(
        self, df: pd.DataFrame, index_columns: list[str], pivot_column: str, meta_columns: list[str]
    ) -> pd.DataFrame:
        """Pivot DataFrame for multi-model comparison."""
        # Get other columns excluding standard deviation columns and metadata columns
        other_columns = [
            col
            for col in df.columns.difference(index_columns + [pivot_column] + meta_columns)
            if ('std_deviation' not in col) and ('calculated_score' not in col)
        ]

        # Only pivot if we have other columns and multiple models
        if other_columns and len(df[pivot_column].unique()) > 1:
            try:
                # Handle duplicate model names by adding unique suffixes
                df = self._handle_duplicate_models(df, pivot_column, index_columns)

                # Ensure pivot columns are numeric where expected
                for col in other_columns:
                    if col.endswith('_score') or col.endswith('_calculated_score') or col.endswith('_std_deviation'):
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                # Pivot the DataFrame
                df_pivot = df.pivot(
                    index=index_columns,
                    columns=pivot_column,
                    values=other_columns,
                )

                # Flatten multi-level columns
                df_pivot.columns = [  # type: ignore[misc]
                    f'{metric}_{model}' for metric, model in df_pivot.columns  # type: ignore[has-type]
                ]

                # Reset index for a standard DataFrame
                df_pivot = df_pivot.reset_index()

                # Merge back non-pivoted metadata columns
                if meta_columns:
                    try:
                        # Prefer metadata from Jury row if available (fuzzy match for Jury variants)
                        jury_rows = df[df[pivot_column].apply(self._is_jury_model)]
                        if not jury_rows.empty:
                            meta_df = jury_rows[index_columns + meta_columns].copy()
                        else:
                            meta_df = df[index_columns + meta_columns].copy()

                        # Normalize complex objects to JSON strings for stable dedup/merge
                        for mc in meta_columns:
                            meta_df[mc] = meta_df[mc].apply(
                                lambda v: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                            )
                        meta_df = meta_df.drop_duplicates(subset=index_columns)
                        df_pivot = pd.merge(df_pivot, meta_df, on=index_columns, how='left')
                    except Exception as merge_ex:
                        self.logger.warning(f'Failed to merge metadata columns: {merge_ex}')
            except Exception as e:
                self.logger.warning(f'Pivoting failed, using original DataFrame: {e}')
                df_pivot = df
        else:
            # No pivoting needed, use original DataFrame
            df_pivot = df

        return df_pivot

    def _add_calculated_scores(
        self, df_pivot: pd.DataFrame, df: pd.DataFrame, index_columns: list[str]
    ) -> pd.DataFrame:
        """Add calculated score columns for Jury model if available."""
        # Find Jury score columns (fuzzy match for any Jury variant)
        jury_score_cols = [
            col for col in df_pivot.columns if '_score_' in col and self._is_jury_model(col.split('_score_')[-1])
        ]

        for score_col in jury_score_cols:
            # Extract axis (everything before _score_)
            axis = score_col.split('_score_')[0]
            calc_col = f'{axis}_calculated_score'

            if calc_col in df.columns:
                # Find jury rows using fuzzy matching
                jury_calc = df[df['model'].apply(self._is_jury_model)][index_columns + [calc_col]]
                if not jury_calc.empty:
                    df_pivot[calc_col] = jury_calc[calc_col].iloc[0]

        return df_pivot

    def _order_columns(self, df_pivot: pd.DataFrame, index_columns: list[str]) -> pd.DataFrame:
        """Apply comprehensive column ordering for readability."""
        try:
            cols_all = list(df_pivot.columns)
            ordered: list[str] = []

            # 1) Index columns
            ordered.extend([c for c in index_columns if c in cols_all])

            # 2) Metadata columns (in preferred order)
            ordered.extend(self._get_ordered_metadata_columns(cols_all, ordered))

            # 3) Model suffixes (Jury model at end)
            model_suffixes = self._extract_model_suffixes(cols_all)

            # 4) Axes (evaluation criteria)
            axes = self._extract_axes(cols_all)

            # 5) Score/Reasoning/Calculated columns for each axis and model
            ordered.extend(self._get_ordered_score_columns(cols_all, axes, model_suffixes, ordered))

            # 6) Overall fields
            ordered.extend(self._get_ordered_overall_columns(cols_all, ordered))

            # 7) Remaining columns
            remaining = [c for c in cols_all if c not in ordered]
            df_pivot = df_pivot[ordered + remaining]
        except Exception as ex:
            self.logger.warning(f'Unable to apply column ordering: {ex}')

        return df_pivot

    def _get_ordered_metadata_columns(self, all_cols: list[str], exclude: list[str]) -> list[str]:
        """Get metadata columns in preferred order."""
        preferred_meta = ['source', 'response', 'response_a', 'response_b', 'question']
        ordered = [c for c in preferred_meta if c in all_cols and c not in exclude]

        # Add definition columns (e.g., accuracy_definition, qna_definition, comparison_definition)
        definition_cols = sorted([c for c in all_cols if c.endswith('_definition') and c not in exclude])
        ordered.extend(definition_cols)

        return ordered

    def _extract_model_suffixes(self, all_cols: list[str]) -> list[str]:
        """Extract unique model suffixes from score columns, with Jury model at end."""
        suffixes = []
        for col in all_cols:
            # All modes use pattern: '{prefix}_score_{model}'
            if '_score_' in col:
                parts = col.split('_score_')
                if len(parts) == 2:
                    suffixes.append(parts[1])

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_suffixes = [s for s in suffixes if not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]

        # Move all Jury variants to end for readability (fuzzy match)
        jury_models = [s for s in unique_suffixes if self._is_jury_model(s)]
        non_jury_models = [s for s in unique_suffixes if not self._is_jury_model(s)]

        return non_jury_models + jury_models

    def _extract_axes(self, all_cols: list[str]) -> set[str]:
        """Extract evaluation axes (criteria/prefixes) from column names."""
        patterns = ['_score_', '_reasoning_', '_calculated_score', '_std_deviation']
        axes = set()
        for col in all_cols:
            for pattern in patterns:
                if pattern in col:
                    axes.add(col.split(pattern)[0])
                    break
        return {a for a in axes if a}

    def _get_ordered_score_columns(
        self, all_cols: list[str], axes: set[str], models: list[str], exclude: list[str]
    ) -> list[str]:
        """Get score, reasoning, and calculated score columns in order."""
        ordered = []

        for axis in sorted(axes):
            for model in models:
                # All modes use consistent pattern: '{prefix}_score_{model}'
                for col_type in ['score', 'reasoning']:
                    col = f'{axis}_{col_type}_{model}'
                    if col in all_cols and col not in exclude and col not in ordered:
                        ordered.append(col)
                        # Add calculated score after Jury score (fuzzy match)
                        if col_type == 'score' and self._is_jury_model(model):
                            calc_col = f'{axis}_calculated_score'
                            if calc_col in all_cols and calc_col not in ordered:
                                ordered.append(calc_col)

            # Std deviation
            std_col = f'{axis}_std_deviation'
            if std_col in all_cols and std_col not in ordered:
                ordered.append(std_col)

        return ordered

    def _get_ordered_overall_columns(self, all_cols: list[str], exclude: list[str]) -> list[str]:
        """Get overall score and reasoning columns."""
        overall_cols = ['overall_score', 'overall_reasoning']
        return [c for c in overall_cols if c in all_cols and c not in exclude]
