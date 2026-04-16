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

"""ag-Grid helper functions for Excel-like data viewing."""

import pandas as pd

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
    from st_aggrid.shared import DataReturnMode

    AGGRID_AVAILABLE = True
except ImportError:
    AGGRID_AVAILABLE = False


# Constants
SCORE_THRESHOLD_HIGH = 4.0
SCORE_THRESHOLD_MED = 3.0
COLOR_HIGH = '#c6efce'  # Green
COLOR_MED = '#ffeb9c'  # Yellow
COLOR_LOW = '#ffc7ce'  # Red

SCORE_COL_WIDTH = 120
TEXT_COL_WIDTH = 300
PINNED_COL_WIDTH = 200
MAX_PINNED_COLS = 2

SCORE_KEYWORDS = ['_score']
TEXT_KEYWORDS = ['source', 'response', 'reasoning', 'question', 'answer', 'summary']
PIN_KEYWORDS = ['filename', 'section_id', 'section']


def _get_score_style_jscode(high_threshold=None, med_threshold=None):
    """Get JsCode for score column color coding."""
    high = high_threshold if high_threshold is not None else SCORE_THRESHOLD_HIGH
    med = med_threshold if med_threshold is not None else SCORE_THRESHOLD_MED

    return JsCode(
        f"""
        function(params) {{
            if (params.value == null) return {{'backgroundColor': 'white'}};
            if (params.value >= {high}) {{
                return {{'color': 'black', 'backgroundColor': '{COLOR_HIGH}', 'fontWeight': 'bold'}};
            }} else if (params.value >= {med}) {{
                return {{'color': 'black', 'backgroundColor': '{COLOR_MED}'}};
            }} else {{
                return {{'color': 'black', 'backgroundColor': '{COLOR_LOW}'}};
            }}
        }};
    """
    )


def _detect_columns_by_type(df):
    """Detect score and text columns."""
    score_cols = [c for c in df.columns if any(kw in c for kw in SCORE_KEYWORDS)]
    text_cols = [c for c in df.columns if any(kw in c.lower() for kw in TEXT_KEYWORDS)]
    return score_cols, text_cols


def _auto_detect_pinned_cols(df):
    """Auto-detect columns to pin."""
    pinned = []
    for col in df.columns:
        if any(kw in col.lower() for kw in PIN_KEYWORDS):
            pinned.append(col)
            if len(pinned) >= MAX_PINNED_COLS:
                break
    return pinned


def _configure_base_grid(gb, enable_enterprise, pre_select_all=False):
    """Configure base grid options."""
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
    gb.configure_side_bar(filters_panel=True, columns_panel=True, defaultToolPanel='columns')
    gb.configure_default_column(
        groupable=enable_enterprise,
        value=True,
        enableRowGroup=enable_enterprise,
        editable=False,
        filterable=True,
        sortable=True,
        resizable=True,
        wrapText=False,
        autoHeight=False,
        minWidth=100,
        maxWidth=400,
    )
    # Configure selection
    gb.configure_selection(
        selection_mode='multiple',
        use_checkbox=True,
        rowMultiSelectWithClick=False,
        suppressRowDeselection=False,
    )

    # Configure grid options for better UX
    other_options = {
        'suppressRowClickSelection': False,  # Allow row click to select
        'enableCellTextSelection': True,  # Enable text selection in cells
        'ensureDomOrder': True,  # Better for accessibility
        'enableBrowserTooltips': True,  # Show tooltips on hover
        'rowSelection': 'multiple',  # Enable multiple row selection
        'suppressCellSelection': False,  # Allow cell selection for copying
        'enableRangeSelection': True,  # Enable range selection for copying
    }

    # If pre_select_all, use onGridReady to select all rows and check header checkbox
    if pre_select_all:
        other_options['onGridReady'] = JsCode(
            """
            function(params) {
                params.api.selectAll();
            }
        """
        )

    gb.configure_grid_options(**other_options)


def _configure_pinned_cols(gb, df, pinned_cols):
    """Configure pinned columns with header checkbox that reflects selection state."""
    pinned_cols = pinned_cols if pinned_cols is not None else _auto_detect_pinned_cols(df)
    for idx, col in enumerate(pinned_cols):
        if col in df.columns:
            # Add header checkbox to first pinned column for select all
            if idx == 0:
                gb.configure_column(
                    col,
                    pinned='left',
                    lockPosition=True,
                    suppressMovable=True,
                    width=PINNED_COL_WIDTH,
                    headerCheckboxSelection=True,
                    checkboxSelection=True,
                    headerCheckboxSelectionFilteredOnly=True,
                )
            else:
                gb.configure_column(
                    col,
                    pinned='left',
                    lockPosition=True,
                    suppressMovable=True,
                    width=PINNED_COL_WIDTH,
                )


def _configure_score_cols(gb, score_cols, high_threshold=None, med_threshold=None):
    """Configure score columns with color coding."""
    style_js = _get_score_style_jscode(high_threshold, med_threshold)
    for col in score_cols:
        gb.configure_column(
            col,
            cellStyle=style_js,
            type=['numericColumn', 'numberColumnFilter'],
            width=SCORE_COL_WIDTH,
        )


def _configure_text_cols(gb, text_cols):
    """Configure text columns for easy reading, copying, and expanding."""
    for col in text_cols:
        gb.configure_column(
            col,
            wrapText=True,  # Enable text wrapping
            autoHeight=True,  # Auto-expand row height to show full content
            width=TEXT_COL_WIDTH,
            tooltipField=col,
            cellStyle={
                'whiteSpace': 'nowrap',  # Preserve whitespace and wrap
                'cursor': 'text',  # Text cursor for selection
                'userSelect': 'text',  # Enable text selection
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
            },
            cellClass='text-cell-selectable',
            editable=False,
            cellRenderer=None,  # Use default renderer for text selection
        )


def create_aggrid_config(
    df: pd.DataFrame,
    enable_enterprise: bool = False,
    pinned_cols: list = None,
    score_thresholds: tuple = None,
    pre_select_all: bool = False,
) -> dict:
    """
    Create ag-Grid configuration for Excel-like viewing.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to display
    enable_enterprise : bool, default=False
        Enable enterprise features (grouping, etc.)
    pinned_cols : list, optional
        Columns to pin to left side
    score_thresholds : tuple, optional
        (high_threshold, med_threshold) for color coding
    pre_select_all : bool, default=False
        Pre-select all rows

    Returns
    -------
    dict
        ag-Grid configuration
    """
    gb = GridOptionsBuilder.from_dataframe(df)

    # Configure base grid
    _configure_base_grid(gb, enable_enterprise, pre_select_all)

    # Configure pinned columns
    _configure_pinned_cols(gb, df, pinned_cols)

    # Detect and configure column types
    score_cols, text_cols = _detect_columns_by_type(df)

    # Pass thresholds if provided
    if score_thresholds:
        high_thresh, med_thresh = score_thresholds
        _configure_score_cols(gb, score_cols, high_thresh, med_thresh)
    else:
        _configure_score_cols(gb, score_cols)

    _configure_text_cols(gb, text_cols)

    return gb.build()


def display_aggrid(
    df: pd.DataFrame,
    height: int = 400,
    enable_enterprise: bool = False,
    fit_columns: bool = False,
    theme: str = 'streamlit',
    pinned_cols: list = None,
    score_thresholds: tuple = None,
    pre_select_all: bool = False,
) -> dict:
    """
    Display DataFrame using ag-Grid with Excel-like features.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to display
    height : int, default=400
        Grid height in pixels
    enable_enterprise : bool, default=False
        Enable enterprise features
    fit_columns : bool, default=False
        Auto-fit columns to content
    theme : str, default='streamlit'
        Theme: 'streamlit', 'alpine', 'balham', 'material'
    pinned_cols : list, optional
        Columns to pin to left (auto-detected if None)
    score_thresholds : tuple, optional
        (high_threshold, med_threshold) for dynamic color coding
    pre_select_all : bool, default=False
        Pre-select all rows on initial load

    Returns
    -------
    dict
        Grid response with selected rows and data
    """
    if not AGGRID_AVAILABLE:
        raise ImportError('streamlit-aggrid not installed. Run: pip install streamlit-aggrid')

    grid_options = create_aggrid_config(df, enable_enterprise, pinned_cols, score_thresholds, pre_select_all)

    # Display with ag-Grid
    # Selection handled by onGridReady callback in grid_options when pre_select_all=True
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=fit_columns,
        theme=theme,
        height=height,
        enable_enterprise_modules=enable_enterprise,
        allow_unsafe_jscode=True,
        reload_data=False,
    )

    return grid_response


def is_aggrid_available() -> bool:
    """Check if ag-Grid is available."""
    return AGGRID_AVAILABLE
