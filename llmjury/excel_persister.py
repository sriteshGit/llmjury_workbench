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
Excel Persister Operator for LLM Jury evaluation.

This operator handles saving DataFrames to Excel files with
conditional formatting for score visualization.
"""

import logging
import re
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pandas as pd
from openpyxl.styles import Alignment, Font  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from venice.core.Operator import Operator

from llmjury.constants import (
    COMPRESSION_RATIO_COL,
    PERCENTAGE_THRESHOLD,
    SCORE_SUFFIX,
    SCORE_THRESHOLD,
    STD_DEV_SUFFIX,
    ExcelColor,
)


class LLMJuryExcelPersister(Operator):
    """
    Save evaluation results to formatted Excel files.

    This operator creates Excel files with multiple sheets and applies
    conditional formatting to visualize scores and performance metrics.

    Features (all configurable via flags):
    - Header formatting (bold, centered)
    - Score column conditional formatting (red/green)
    - Percentage column conditional formatting (red/green)
    - Compression ratio 5-tier formatting
    - Automatic column width adjustment
    """

    VERSION = '0.1.0'

    def __init__(
        self,
        dfs: dict[str, pd.DataFrame],
        filename: str,
        folder_path: Path,
        logger: logging.Logger | None = None,
        score_threshold: float | None = None,
        percentage_threshold: int | None = None,
    ):
        """
        Initialize Excel persister.

        Args
        ----
            dfs: Dictionary of DataFrames to save (key: sheet name, value: DataFrame)
            filename: Name of the file (with or without .xlsx extension)
            folder_path: Path to the folder where the file should be saved
            logger: Optional logger instance
            score_threshold: Optional score threshold for formatting (defaults to constant)
            percentage_threshold: Optional percentage threshold for formatting (defaults to constant)
        """
        super().__init__()
        self.dfs = dfs
        self.filename = filename if filename.endswith('.xlsx') else f'{filename}.xlsx'
        self.folder_path = Path(folder_path)
        self.logger = logger or logging.getLogger(__name__)

        # Thresholds
        self.score_threshold = score_threshold if score_threshold is not None else SCORE_THRESHOLD
        self.percentage_threshold = percentage_threshold if percentage_threshold is not None else PERCENTAGE_THRESHOLD

    def run(self) -> Path:
        """
        Save DataFrames to Excel file with formatting.

        Returns
        -------
            Path to the created Excel file

        Raises
        ------
            OSError: If there are issues with file operations
            ValueError: If DataFrame cannot be written to Excel
        """
        try:
            file_path = self.folder_path / self.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                for sheet_name, df in self.dfs.items():
                    if df.empty:
                        self.logger.warning(f'Skipping empty DataFrame for sheet: {sheet_name}')
                        continue

                    # Sanitize DataFrame to remove illegal Excel characters
                    df_sanitized = self._sanitize_dataframe(df)

                    # Write DataFrame to Excel
                    df_sanitized.to_excel(writer, sheet_name=sheet_name, index=False)
                    worksheet = writer.sheets[sheet_name]

                    # Apply formatting
                    self._apply_sheet_formatting(worksheet, df_sanitized, sheet_name)

            self.logger.info(f'Successfully saved Excel file: {file_path}')
            return file_path

        except (OSError, ValueError) as e:
            self.logger.error(f'Error saving Excel file {self.filename}: {e}')
            raise

    def _sanitize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Sanitize DataFrame by removing illegal characters for Excel.

        Excel doesn't allow control characters (ASCII 0-31 except tab, newline, carriage return).
        This method removes those characters from all string cells.

        Args
        ----
            df: DataFrame to sanitize

        Returns
        -------
            Sanitized copy of the DataFrame
        """
        df_copy = df.copy()

        # Pattern to match illegal Excel characters
        # Excel doesn't allow control characters except \t (09), \n (0A), \r (0D)
        illegal_chars_pattern = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')

        # Apply sanitization to all object (string) columns
        for col in df_copy.columns:
            if df_copy[col].dtype == 'object':
                df_copy[col] = df_copy[col].apply(
                    lambda x: illegal_chars_pattern.sub('', str(x)) if pd.notna(x) and isinstance(x, str) else x
                )

        return df_copy

    def _apply_sheet_formatting(
        self,
        worksheet: openpyxl.worksheet.worksheet.Worksheet,
        df: pd.DataFrame,
        sheet_name: str,
    ) -> None:
        """
        Apply all formatting to sheet.

        Each formatting method checks if relevant columns exist, so it's
        safe and efficient to apply all formatting to all sheets.
        """
        # Apply all formatting (methods handle missing columns)
        self._format_headers(worksheet, df)
        self._format_score_columns(worksheet, df)

        # Additional formatting methods (commented out pending requirements)
        # Uncomment when enhanced formatting is requested:
        # self._format_percentage_columns(worksheet, df)      # Colors percentage columns
        # self._format_compression_column(worksheet, df)       # 5-tier compression ratio colors
        # self._auto_adjust_columns(worksheet, df)             # Auto-adjust column widths

    def _format_headers(self, worksheet: openpyxl.worksheet.worksheet.Worksheet, df: pd.DataFrame) -> None:
        """Format header row with bold font and alignment."""
        header_font = Font(bold=True, size=11)
        for col_idx in range(1, len(df.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

    def _auto_adjust_columns(
        self, worksheet: openpyxl.worksheet.worksheet.Worksheet, df: pd.DataFrame, max_width: int = 50
    ) -> None:
        """Auto-adjust column widths based on content."""
        for col_idx, column in enumerate(df.columns, start=1):
            column_letter = get_column_letter(col_idx)
            max_length = len(str(column))  # Start with header length

            for row_idx in range(2, min(len(df) + 2, 100)):  # Limit to first 100 rows for performance
                cell_value = worksheet.cell(row=row_idx, column=col_idx).value
                if cell_value:
                    max_length = max(max_length, len(str(cell_value)))

            adjusted_width = min(max_length + 2, max_width)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    def _apply_conditional_format(
        self, worksheet: openpyxl.worksheet.worksheet.Worksheet, row: int, col: int, value: float, threshold: float
    ) -> None:
        """
        Apply conditional formatting to a cell based on threshold.

        Silently handles ValueError/TypeError for cells with non-numeric values,
        as some cells may contain strings or other non-numeric data that should be skipped.
        """
        try:
            cell = worksheet.cell(row=row, column=col)
            cell.fill = ExcelColor.RED.value if value <= threshold else ExcelColor.GREEN.value
            cell.number_format = '0.00'
        except (ValueError, TypeError):
            # Skip cells with non-numeric values
            pass

    def _format_score_columns(self, worksheet: openpyxl.worksheet.worksheet.Worksheet, df: pd.DataFrame) -> None:
        """Format score columns with conditional formatting."""
        score_columns = [
            col
            for col in df.columns
            if SCORE_SUFFIX in col and STD_DEV_SUFFIX not in col and 'sections with >' not in col
        ]

        for col_name in score_columns:
            col_idx = int(df.columns.get_loc(col_name)) + 1  # type: ignore[arg-type]
            for row in range(2, len(df) + 2):
                cell = worksheet.cell(row=row, column=col_idx)
                if cell.value is not None:
                    self._apply_conditional_format(worksheet, row, col_idx, float(cell.value), self.score_threshold)

    def _format_percentage_columns(self, worksheet: openpyxl.worksheet.worksheet.Worksheet, df: pd.DataFrame) -> None:
        """Format percentage columns with conditional formatting."""
        percentage_columns = [
            col for col in df.columns if 'percentage' in col.lower() and 'compression' not in col.lower()
        ]

        for col_name in percentage_columns:
            col_idx = int(df.columns.get_loc(col_name)) + 1  # type: ignore[arg-type]
            for row in range(2, len(df) + 2):
                cell = worksheet.cell(row=row, column=col_idx)
                if cell.value is not None:
                    self._apply_conditional_format(
                        worksheet, row, col_idx, float(cell.value), self.percentage_threshold
                    )

    def _format_compression_column(
        self,
        worksheet: openpyxl.worksheet.worksheet.Worksheet,
        df: pd.DataFrame,
        col_name: str | None = None,
    ) -> None:
        """
        Format compression ratio column with 5-tier color scheme.

        Color tiers:
        - < 5.0: Red (very low compression)
        - 5.0-7.5: Misty rose (low compression)
        - 7.5-10.0: Lavender (medium compression)
        - 10.0-15.0: Honeydew (good compression)
        - >= 15.0: Red (too high compression, potential information loss)
        """
        # Use constant for default column name
        if col_name is None:
            col_name = COMPRESSION_RATIO_COL

        if col_name not in df.columns:
            return

        col_idx = int(df.columns.get_loc(col_name)) + 1  # type: ignore[arg-type]

        for row in range(2, len(df) + 2):
            cell = worksheet.cell(row=row, column=col_idx)
            if cell.value is None:
                continue

            try:
                ratio = float(cell.value)
                if ratio < 5.0:
                    cell.fill = ExcelColor.RED.value
                elif ratio < 7.5:
                    cell.fill = ExcelColor.MISTY_ROSE.value
                elif ratio < 10.0:
                    cell.fill = ExcelColor.LAVENDER.value
                elif ratio < 15.0:
                    cell.fill = ExcelColor.HONEYDEW.value
                else:
                    cell.fill = ExcelColor.RED.value  # Too high compression
                cell.number_format = '0.00'
            except (ValueError, TypeError):
                continue
