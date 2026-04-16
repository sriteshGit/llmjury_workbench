#   ADOBE CONFIDENTIAL
#   ___________________
#
#   Copyright 2025 Adobe
#   All Rights Reserved.
#
#   NOTICE:  All information contained herein is, and remains
#   the property of Adobe and its suppliers, if any.
#   intellectual and technical concepts contained herein are
#   proprietary to Adobe and its suppliers and are protected
#   by all applicable intellectual property laws, including
#   trade secret and copyright laws.  Dissemination of this
#   information or reproduction of this material is strictly
#   forbidden unless prior written permission is obtained
#   from Adobe.

"""Data loading utilities for LLMJury results."""

import json
from io import BytesIO
from typing import Any

import pandas as pd


def _get_excel_file(file_content: bytes | str) -> pd.ExcelFile:
    """Helper to get ExcelFile from bytes or path."""
    if isinstance(file_content, bytes):
        return pd.ExcelFile(BytesIO(file_content))
    return pd.ExcelFile(file_content)


def _load_json_data(file_content: bytes | str) -> Any:
    """Helper to load JSON from bytes or path."""
    if isinstance(file_content, bytes):
        return json.loads(file_content.decode('utf-8'))
    with open(file_content, encoding='utf-8') as f:
        return json.load(f)


def load_json_results(file_content: bytes | str) -> pd.DataFrame:
    """
    Load results from JSON file.

    Parameters
    ----------
    file_content : bytes | str
        JSON file content or file path

    Returns
    -------
    pd.DataFrame
        Results as DataFrame
    """
    try:
        data = _load_json_data(file_content)

        if isinstance(data, list):
            return pd.DataFrame(data)
        if isinstance(data, dict):
            return pd.DataFrame([data])
        raise ValueError('Invalid JSON format: expected list or dict')
    except Exception as e:
        raise ValueError(f'Error loading JSON: {str(e)}') from e


def load_excel_results(file_content: bytes | str, sheet_name: str = 'merged') -> pd.DataFrame:
    """
    Load results from Excel file.

    Parameters
    ----------
    file_content : bytes | str
        Excel file content or file path
    sheet_name : str, default='merged'
        Sheet name to load

    Returns
    -------
    pd.DataFrame
        Results as DataFrame
    """
    try:
        excel_file = _get_excel_file(file_content)
        return pd.read_excel(excel_file, sheet_name=sheet_name)
    except Exception as e:
        raise ValueError(f'Error loading Excel: {str(e)}') from e


def load_excel_all_sheets(file_content: bytes | str) -> dict[str, pd.DataFrame]:
    """
    Load all sheets from Excel file.

    Parameters
    ----------
    file_content : bytes | str
        Excel file content or file path

    Returns
    -------
    dict[str, pd.DataFrame]
        Dictionary mapping sheet names to DataFrames
    """
    try:
        excel_file = _get_excel_file(file_content)
        return {name: pd.read_excel(excel_file, sheet_name=name) for name in excel_file.sheet_names}
    except Exception as e:
        raise ValueError(f'Error loading Excel sheets: {str(e)}') from e


def get_excel_sheet_names(file_content: bytes | str) -> list[str]:
    """
    Get sheet names from Excel file.

    Parameters
    ----------
    file_content : bytes | str
        Excel file content or file path

    Returns
    -------
    list[str]
        List of sheet names
    """
    try:
        excel_file = _get_excel_file(file_content)
        return excel_file.sheet_names
    except Exception as e:
        raise ValueError(f'Error reading Excel: {str(e)}') from e


def _is_json_file(filename: str) -> bool:
    """Check if filename is JSON."""
    return filename.endswith('.json')


def _is_excel_file(filename: str) -> bool:
    """Check if filename is Excel."""
    return filename.endswith(('.xlsx', '.xls'))


def load_results(uploaded_file: Any = None, file_path: str | None = None) -> pd.DataFrame:
    """
    Load results from either uploaded file or file path.

    Parameters
    ----------
    uploaded_file : Any, optional
        Streamlit UploadedFile object
    file_path : str, optional
        Path to file

    Returns
    -------
    pd.DataFrame
        Results as DataFrame
    """
    # Determine source and filename
    if uploaded_file is not None:
        filename = uploaded_file.name
        content = uploaded_file.read()
    elif file_path is not None:
        filename = file_path
        content = file_path
    else:
        raise ValueError('Either uploaded_file or file_path must be provided')

    # Load based on extension
    if _is_json_file(filename):
        return load_json_results(content)
    if _is_excel_file(filename):
        return load_excel_results(content)
    raise ValueError('Unsupported file format. Use JSON or Excel.')


def get_score_columns(df: pd.DataFrame) -> list[str]:
    """
    Get all score columns from DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame

    Returns
    -------
    list[str]
        List of score column names
    """
    return [col for col in df.columns if col.endswith('_score') and not col.endswith('calculated_score')]


def get_criteria_names(df: pd.DataFrame) -> list[str]:
    """
    Get criteria names from score columns.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame

    Returns
    -------
    list[str]
        List of criteria names
    """
    return [col.replace('_score', '') for col in get_score_columns(df) if col != 'overall_score']


def get_basic_stats(df: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate basic statistics from results.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame

    Returns
    -------
    dict[str, Any]
        Dictionary of statistics
    """
    score_cols = get_score_columns(df)

    stats = {
        'total_sections': len(df),
        'total_models': df['model'].nunique() if 'model' in df.columns else 1,
        'avg_scores': {},
        'min_scores': {},
        'max_scores': {},
    }

    for col in score_cols:
        criteria = col.replace('_score', '')
        stats['avg_scores'][criteria] = df[col].mean()
        stats['min_scores'][criteria] = df[col].min()
        stats['max_scores'][criteria] = df[col].max()

    return stats
