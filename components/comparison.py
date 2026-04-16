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

"""
Side-by-side comparison dashboard for LLMJury results.

This component provides detailed row-level comparison between two evaluation runs:
- Joins results on filename + section_id
- Shows matched rows in a filterable grid
- Displays side-by-side comparison of:
  * Source/Response text
  * All metrics scores
  * Reasoning explanations
  * Difference analysis

Framework-agnostic design using LLMJury patterns and field mappings.
"""

from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.aggrid_helper import display_aggrid, is_aggrid_available  # noqa: E402
from utils.data_loader import load_excel_all_sheets, load_results  # noqa: E402

from llmjury.constants import (  # noqa: E402
    REASONING_SUFFIX,
    SCORE_SUFFIX,
    SheetName,
)
from llmjury.field_mappings import (  # noqa: E402
    ANSWER_FIELD_NAMES,
    PROMPT_FIELD_NAMES,
    QUESTION_FIELD_NAMES,
)

# ============================================================================
# CONSTANTS
# ============================================================================

DEFINITION_SUFFIX = '_definition'
WORD_COUNT_SUFFIX = '_word_count'

# Keywords for field detection
SOURCE_KEYWORDS = ['source', 'prompt', 'context', 'ground_truth', 'reference', 'question']
RESPONSE_KEYWORDS = ['response', 'answer', 'summary', 'output', 'result', 'prediction']
FILE_KEYWORDS = ['filename', 'file']
SECTION_KEYWORDS = ['section_id', 'section']

# Score visualization
SCORE_HIGH_THRESHOLD = 4.0
SCORE_MED_THRESHOLD = 3.0
SCORE_EMOJI_HIGH = '🟢'
SCORE_EMOJI_MED = '🟡'
SCORE_EMOJI_LOW = '🔴'
SCORE_EMOJI_BETTER = '📈'
SCORE_EMOJI_WORSE = '📉'
SCORE_EMOJI_SAME = '➡️'

# Colors for difference highlighting
COLOR_BETTER = '#c6efce'  # Green
COLOR_WORSE = '#ffc7ce'  # Red
COLOR_NEUTRAL = '#e7e6e6'  # Gray
COLOR_GRADIENT = 'RdYlGn'

# Radar chart colors
RADAR_COLORS = {
    'result1': '#3498db',  # Blue
    'result2': '#e74c3c',  # Red
}


# ============================================================================
# MAIN RENDERING FUNCTION
# ============================================================================


def render_comparison_tab():
    """Main entry point for comparison dashboard."""
    st.header('🔬 Side-by-Side Comparison')
    st.markdown('Compare two evaluation runs with detailed row-level analysis')

    # Load data section
    result1_data, result2_data, label1, label2 = load_comparison_data()

    if result1_data is None or result2_data is None:
        show_instructions()
        return

    # Prepare dataframes with sheet selection
    df1, sheet1 = prepare_dataframe(result1_data, 'result1')
    df2, sheet2 = prepare_dataframe(result2_data, 'result2')

    if df1.empty or df2.empty:
        st.warning('One or both datasets are empty')
        return

    # Join on filename + section_id
    joined_df, join_stats = join_datasets(df1, df2, label1, label2)

    if joined_df.empty:
        st.error('❌ No matching rows found between the two results')
        st.info('💡 Joined on: filename + section_id. Ensure both files have these columns with matching values.')
        show_join_diagnostics(df1, df2)
        return

    # Show join statistics
    show_join_stats(join_stats, label1, label2)

    # Filters and search
    search_term, score_filter_metric, min_score, max_score, diff_filter, sort_by, sort_order = render_filters(
        joined_df, label1, label2
    )

    # Apply filters
    filtered_df = apply_filters(
        joined_df,
        search_term,
        score_filter_metric,
        min_score,
        max_score,
        diff_filter,
        sort_by,
        sort_order,
    )

    # Dataset metrics
    show_comparison_metrics(filtered_df, label1, label2)

    # Display comparison grid
    st.markdown('**✨ Select rows for detailed comparison**')
    st.caption(
        '💡 Click checkbox in rows to select | Check header checkbox to select all | '
        'Export & re-analyze options appear below after selection'
    )

    selected_rows = display_comparison_grid(filtered_df, label1, label2)

    # Detailed side-by-side view
    if selected_rows:
        render_sidebyside_comparison(selected_rows, label1, label2)

        # Export for re-analysis (dual-response evaluation)
        st.markdown('---')
        st.caption(f'**📥 Export {len(selected_rows)} selected row{"s" if len(selected_rows) > 1 else ""}:**')

        # Transform to dual-response format for re-analysis
        dual_response_data = prepare_dual_response_format(selected_rows, filtered_df, label1, label2)

        # Store in session state for re-analysis
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                '🔄 Re-analyze Both',
                key='goto_comparison_reanalysis',
                help='Evaluate both responses side-by-side with new criteria',
                type='primary',
                use_container_width=True,
            ):
                st.session_state['dual_response_data'] = dual_response_data
                st.session_state['dual_reanalysis_clicked'] = True
                st.session_state['auto_run_ready'] = True  # Flag for auto-run readiness
                st.rerun()

        with col2:
            # Export as JSON
            import json

            json_data = json.dumps(dual_response_data, indent=2)
            st.download_button(
                '📋 JSON',
                json_data,
                'dual_responses.json',
                'application/json',
                key='export_dual_json',
                use_container_width=True,
            )

        with col3:
            # Export as Excel
            excel_buffer = BytesIO()
            df_export = pd.DataFrame(dual_response_data)
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='dual_responses')
            excel_buffer.seek(0)

            st.download_button(
                '📊 Excel',
                excel_buffer.getvalue(),
                'dual_responses.xlsx',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='export_dual_excel',
                use_container_width=True,
            )

        # Show message after buttons
        if st.session_state.get('dual_reanalysis_clicked', False):
            st.success('✅ Dual-response data ready!')
            st.info('💡 Switch to **🚀 Run Evaluation** tab → **📊 Dashboard Data** will auto-load this data.')
            st.session_state['dual_reanalysis_clicked'] = False
    else:
        st.info('👆 Select one or more rows from the table above to view detailed comparison')


# ============================================================================
# DATA LOADING & PREPARATION
# ============================================================================


def load_comparison_data():
    """Load two result files for comparison."""
    st.markdown('**📤 Upload Two Results to Compare:**')

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('**Result 1 (a)**')
        label1 = st.text_input('Label 1', 'a', key='label1')
        uploaded1 = st.file_uploader(
            'Upload result 1', type=['json', 'xlsx'], key='upload1', label_visibility='collapsed'
        )

        data1 = None
        if uploaded1:
            ext = uploaded1.name.split('.')[-1]
            data1 = load_results(uploaded1) if ext == 'json' else load_excel_all_sheets(uploaded1)

    with col2:
        st.markdown('**Result 2 (b)**')
        label2 = st.text_input('Label 2', 'b', key='label2')
        uploaded2 = st.file_uploader(
            'Upload result 2', type=['json', 'xlsx'], key='upload2', label_visibility='collapsed'
        )

        data2 = None
        if uploaded2:
            ext = uploaded2.name.split('.')[-1]
            data2 = load_results(uploaded2) if ext == 'json' else load_excel_all_sheets(uploaded2)

    return data1, data2, label1, label2


def prepare_dataframe(data, key_prefix):
    """Prepare DataFrame with sheet selection if Excel."""
    if isinstance(data, dict) and 'data' not in data:
        # Multi-sheet Excel
        sheet_names = list(data.keys())
        default_sheet = SheetName.JURY_RESULTS.value if SheetName.JURY_RESULTS.value in sheet_names else sheet_names[0]
        default_idx = sheet_names.index(default_sheet)

        if len(sheet_names) > 1:
            sheet_name = st.selectbox(
                f'📑 Select Sheet ({key_prefix})',
                sheet_names,
                index=default_idx,
                key=f'sheet_{key_prefix}',
            )
            return data[sheet_name], sheet_name
        return data[sheet_names[0]], sheet_names[0]

    # JSON or single sheet
    df = pd.DataFrame(data.get('data', data)) if isinstance(data, dict) else pd.DataFrame(data)
    return df, 'Data'


def join_datasets(df1, df2, label1, label2):
    """
    Join two datasets on filename + section_id, with fallback to filename only.

    Strategy:
    1. Try composite key: filename + section_id
    2. If no matches, fall back to filename only

    Returns:
        joined_df: DataFrame with columns prefixed by label
        join_stats: Dictionary with join statistics
    """
    # Find join columns
    file_col = find_column_by_keywords(df1.columns, FILE_KEYWORDS)
    section_col = find_column_by_keywords(df1.columns, SECTION_KEYWORDS)

    if not file_col:
        st.error('❌ Filename column not found. Need: filename-like column')
        return pd.DataFrame(), {}

    # Ensure file column exists in both dataframes
    if file_col not in df2.columns:
        st.error(f'❌ Filename column not found in both datasets: {file_col}')
        return pd.DataFrame(), {}

    # Make copies
    df1 = df1.copy()
    df2 = df2.copy()

    join_method = 'composite'  # Default join method

    # Try composite key join first (if section_col exists in both)
    if section_col and section_col in df1.columns and section_col in df2.columns:
        # Create composite join keys
        df1['_join_key'] = df1[file_col].astype(str) + '::' + df1[section_col].astype(str)
        df2['_join_key'] = df2[file_col].astype(str) + '::' + df2[section_col].astype(str)

        # Try joining on composite key
        joined = df1.merge(df2, on='_join_key', how='inner', suffixes=(f'_{label1}', f'_{label2}'))

        # If no matches, try fallback to filename only
        if joined.empty:
            st.warning(f'⚠️ No matches on composite key ({file_col}::{section_col}). Trying filename-only join...')
            join_method = 'filename_only'

            # Use filename as join key
            df1['_join_key'] = df1[file_col].astype(str)
            df2['_join_key'] = df2[file_col].astype(str)

            # Join on filename only
            joined = df1.merge(df2, on='_join_key', how='inner', suffixes=(f'_{label1}', f'_{label2}'))

            if not joined.empty:
                st.success(f'✅ Found {len(joined)} matches using filename-only join')
    else:
        # No section column available, use filename only
        st.info('ℹ️ Section column not found. Joining on filename only.')
        join_method = 'filename_only'

        # Use filename as join key
        df1['_join_key'] = df1[file_col].astype(str)
        df2['_join_key'] = df2[file_col].astype(str)

        # Join on filename only
        joined = df1.merge(df2, on='_join_key', how='inner', suffixes=(f'_{label1}', f'_{label2}'))

    # Calculate join statistics
    join_stats = {
        'total_result1': len(df1),
        'total_result2': len(df2),
        'matched': len(joined),
        'unmatched_result1': len(df1) - len(joined),
        'unmatched_result2': len(df2) - len(joined),
        'file_col': file_col,
        'section_col': section_col if section_col and section_col in df1.columns else None,
        'join_method': join_method,
    }

    return joined, join_stats


# ============================================================================
# UI COMPONENTS - FILTERS & STATS
# ============================================================================


def render_filters(joined_df, label1, label2):
    """Render filter controls for comparison view."""
    with st.expander('🔍 Filters & Search', expanded=True):
        # Row 1: Search and metric filter
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            search_term = st.text_input('🔎 Search', '', key='comp_search', placeholder='Search across all columns...')

        with col2:
            # Get score columns from either side
            score_cols = [c for c in joined_df.columns if SCORE_SUFFIX in c]

            # Extract base metric names (without label suffixes)
            base_metrics = set()
            for col in score_cols:
                # Remove label suffix to get base metric name
                if f'_{label1}' in col:
                    base_metrics.add(col.replace(f'_{label1}', ''))
                elif f'_{label2}' in col:
                    base_metrics.add(col.replace(f'_{label2}', ''))

            score_filter_metric = st.selectbox('Filter by Metric', ['All'] + sorted(base_metrics), key='comp_metric')

            if score_filter_metric != 'All':
                min_val, max_val = st.slider('Score Range', 0.0, 5.0, (0.0, 5.0), 0.1, key='comp_score_range')
            else:
                min_val, max_val = 0.0, 5.0

        with col3:
            diff_filter = st.selectbox(
                'Difference Filter',
                ['All', 'Improved', 'Degraded', 'Changed', 'Unchanged'],
                key='comp_diff_filter',
                help='Filter by score differences between runs',
            )

        # Row 2: Sort options
        col4, col5 = st.columns(2)

        with col4:
            # Build sort options
            sort_opts = ['_join_key']

            # Add absolute difference columns if they exist
            diff_cols = [c for c in joined_df.columns if c.startswith('_diff_')]
            sort_opts.extend(diff_cols[:5])

            sort_by = st.selectbox('Sort by', sort_opts, key='comp_sort')

        with col5:
            sort_order = st.radio('Order', ['Desc', 'Asc'], horizontal=True, key='comp_order')

    return search_term, score_filter_metric, min_val, max_val, diff_filter, sort_by, sort_order


def apply_filters(df, search_term, score_filter_metric, min_score, max_score, diff_filter, sort_by, sort_order):
    """Apply all filters to comparison dataframe."""
    result = df.copy()

    # Text search
    if search_term:
        mask = result.astype(str).apply(lambda row: search_term.lower() in ' '.join(row).lower(), axis=1)
        result = result[mask]

    # Score filter
    if score_filter_metric != 'All':
        # Find columns for this metric in both results
        metric_cols = [c for c in result.columns if score_filter_metric in c and SCORE_SUFFIX in c]
        if metric_cols:
            # Filter if either result's score is in range
            mask = pd.Series([False] * len(result), index=result.index)
            for col in metric_cols:
                mask |= (result[col] >= min_score) & (result[col] <= max_score)
            result = result[mask]

    # Difference filter
    if diff_filter != 'All':
        # Get all diff columns
        diff_cols = [c for c in result.columns if c.startswith('_diff_')]
        if diff_cols:
            mask = pd.Series([False] * len(result), index=result.index)

            for col in diff_cols:
                if diff_filter == 'Improved':
                    mask |= result[col] > 0.1  # Threshold for meaningful improvement
                elif diff_filter == 'Degraded':
                    mask |= result[col] < -0.1
                elif diff_filter == 'Changed':
                    mask |= abs(result[col]) > 0.1
                elif diff_filter == 'Unchanged':
                    mask |= abs(result[col]) <= 0.1

            result = result[mask]

    # Sort
    if sort_by and sort_by in result.columns:
        result = result.sort_values(sort_by, ascending=(sort_order == 'Asc'))

    return result


def show_join_stats(join_stats, label1, label2):
    """Display join statistics."""
    cols = st.columns(5)
    cols[0].metric(f'{label1} Rows', join_stats['total_result1'])
    cols[1].metric(f'{label2} Rows', join_stats['total_result2'])
    cols[2].metric('✅ Matched', join_stats['matched'])
    cols[3].metric(f'❌ Unmatched ({label1})', join_stats['unmatched_result1'])
    cols[4].metric(f'❌ Unmatched ({label2})', join_stats['unmatched_result2'])

    # Show join method
    join_method = join_stats.get('join_method', 'composite')
    if join_method == 'composite':
        join_desc = f'`{join_stats["file_col"]}` + `{join_stats["section_col"]}`'
    else:
        join_desc = f'`{join_stats["file_col"]}` only'

    st.caption(f'Joined on: {join_desc}')


def show_comparison_metrics(filtered_df, label1, label2):
    """Show aggregate comparison metrics."""
    with st.expander('📊 Score Comparison Summary', expanded=False):
        # Find all score columns
        score_cols_1 = [c for c in filtered_df.columns if SCORE_SUFFIX in c and c.endswith(f'_{label1}')]
        score_cols_2 = [c for c in filtered_df.columns if SCORE_SUFFIX in c and c.endswith(f'_{label2}')]

        if not score_cols_1 or not score_cols_2:
            st.info('No score columns found')
            return

        # Calculate averages
        comparison_data = []
        for col1 in score_cols_1:
            # Find corresponding column in result2
            base_name = col1.replace(f'_{label1}', '')
            col2 = base_name + f'_{label2}'

            if col2 in score_cols_2:
                metric_name = base_name.replace(SCORE_SUFFIX, '')
                avg1 = filtered_df[col1].mean()
                avg2 = filtered_df[col2].mean()
                diff = avg2 - avg1

                comparison_data.append(
                    {
                        'Metric': metric_name,
                        f'{label1} Avg': avg1,
                        f'{label2} Avg': avg2,
                        'Difference': diff,
                        'Change %': (diff / avg1 * 100) if avg1 != 0 else 0,
                        'Status': get_diff_emoji(diff),
                    }
                )

        if comparison_data:
            comp_df = pd.DataFrame(comparison_data)

            # Style the dataframe
            styled = (
                comp_df.style.format(
                    {
                        f'{label1} Avg': '{:.2f}',
                        f'{label2} Avg': '{:.2f}',
                        'Difference': '{:.2f}',
                        'Change %': '{:.1f}%',
                    }
                )
                .background_gradient(subset=[f'{label1} Avg', f'{label2} Avg'], cmap=COLOR_GRADIENT, vmin=0, vmax=5)
                .map(
                    lambda v: (
                        f'background-color: {COLOR_BETTER}'
                        if v > 0.1
                        else (f'background-color: {COLOR_WORSE}' if v < -0.1 else f'background-color: {COLOR_NEUTRAL}')
                    ),
                    subset=['Difference'],
                )
            )

            st.dataframe(styled, width='stretch', height=min(400, len(comp_df) * 35 + 50))


def show_join_diagnostics(df1, df2):
    """Show diagnostic information when join fails."""
    with st.expander('🔍 Join Diagnostics', expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('**Result 1 Columns:**')
            st.write(list(df1.columns))

            file_col = find_column_by_keywords(df1.columns, FILE_KEYWORDS)
            section_col = find_column_by_keywords(df1.columns, SECTION_KEYWORDS)

            if file_col and section_col:
                st.markdown('**Sample keys (first 5):**')
                sample_keys = (df1[file_col].astype(str) + '::' + df1[section_col].astype(str)).head()
                st.code('\n'.join(sample_keys.tolist()))

        with col2:
            st.markdown('**Result 2 Columns:**')
            st.write(list(df2.columns))

            file_col = find_column_by_keywords(df2.columns, FILE_KEYWORDS)
            section_col = find_column_by_keywords(df2.columns, SECTION_KEYWORDS)

            if file_col and section_col:
                st.markdown('**Sample keys (first 5):**')
                sample_keys = (df2[file_col].astype(str) + '::' + df2[section_col].astype(str)).head()
                st.code('\n'.join(sample_keys.tolist()))


# ============================================================================
# GRID DISPLAY
# ============================================================================


def display_comparison_grid(filtered_df, label1, label2):
    """Display comparison grid with score differences highlighted."""
    # Select display columns and compute differences
    display_df = prepare_display_dataframe(filtered_df, label1, label2)

    if display_df.empty:
        st.warning('No data to display')
        return []

    if is_aggrid_available():
        grid = display_aggrid(
            display_df,
            height=400,
            theme='streamlit',
            fit_columns=False,
            pre_select_all=False,  # Don't pre-select for comparison view
        )

        selected = grid.get('selected_rows', [])

        # Handle different return types from ag-Grid
        if isinstance(selected, pd.DataFrame):
            # ag-Grid returned DataFrame
            if not selected.empty:
                selected_full = []
                for i in range(len(selected)):
                    sel_row = selected.iloc[i]
                    join_key = sel_row.get('_join_key', '')
                    full_row = filtered_df[filtered_df['_join_key'] == join_key]
                    if not full_row.empty:
                        selected_full.append(full_row.iloc[0])
                return selected_full
        elif isinstance(selected, list) and len(selected) > 0:
            # ag-Grid returned list
            selected_full = []
            for sel_row in selected:
                join_key = sel_row.get('_join_key', '')
                full_row = filtered_df[filtered_df['_join_key'] == join_key]
                if not full_row.empty:
                    selected_full.append(full_row.iloc[0])
            return selected_full
    else:
        st.dataframe(display_df, width='stretch', height=400)
        idx = st.number_input('Row index', 0, len(display_df) - 1, 0, key='comp_idx')
        join_key = display_df.iloc[idx]['_join_key']
        return [filtered_df[filtered_df['_join_key'] == join_key].iloc[0]]

    return []


def prepare_display_dataframe(df, label1, label2):
    """Prepare dataframe for grid display with score differences."""
    # Find all score columns
    score_cols_1 = sorted([c for c in df.columns if SCORE_SUFFIX in c and c.endswith(f'_{label1}')])
    score_cols_2 = sorted([c for c in df.columns if SCORE_SUFFIX in c and c.endswith(f'_{label2}')])

    # Create display dataframe with interleaved scores and differences
    display_data = []
    for _, row in df.iterrows():
        display_row = {'_join_key': row['_join_key']}

        # For each metric, show: score1, score2, diff
        for col1 in score_cols_1:
            base_name = col1.replace(f'_{label1}', '')
            col2 = base_name + f'_{label2}'

            if col2 in score_cols_2:
                metric_name = base_name.replace(SCORE_SUFFIX, '')
                score1 = row[col1]
                score2 = row[col2]
                diff = score2 - score1 if pd.notna(score1) and pd.notna(score2) else None

                display_row[f'{metric_name} ({label1})'] = score1
                display_row[f'{metric_name} ({label2})'] = score2
                display_row[f'Δ {metric_name}'] = diff

        display_data.append(display_row)

    return pd.DataFrame(display_data)


# ============================================================================
# SIDE-BY-SIDE DETAILED COMPARISON
# ============================================================================


def render_sidebyside_comparison(selected_rows, label1, label2):
    """Render detailed side-by-side comparison for selected rows."""
    num_selected = len(selected_rows)

    st.markdown('---')
    st.markdown(f'### 🔍 Detailed Comparison ({num_selected} row{"s" if num_selected > 1 else ""})')

    # Row selector if multiple selected
    if num_selected > 1:
        options = [row['_join_key'] for row in selected_rows]
        selected_key = st.selectbox('Select row to compare', options, key='sidebyside_selector')
        row = [r for r in selected_rows if r['_join_key'] == selected_key][0]
    else:
        row = selected_rows[0]

    # Display identifier
    st.caption(f'**📍 {row["_join_key"]}**')

    # Side-by-side content comparison
    render_content_comparison(row, label1, label2)

    # Side-by-side metrics comparison
    render_metrics_comparison(row, label1, label2)


def render_content_comparison(row, label1, label2):
    """Render side-by-side content comparison (source/response) with fullscreen and adjustable width options."""
    # Header with controls
    col_title, col_width, col_height, col_fullscreen = st.columns([3, 1, 1, 1])

    with col_title:
        st.markdown('#### 📄 Content Comparison')

    with col_width:
        # Column width ratio selector
        width_ratio = st.selectbox(
            '⬌ Width',
            options=['50:50', '40:60', '60:40', '30:70', '70:30'],
            index=0,
            key='content_width_ratio',
            label_visibility='visible',
        )

    with col_height:
        # Height selector
        height_mode = st.selectbox(
            '⬍ Height',
            options=['Small', 'Medium', 'Large', 'XLarge'],
            index=1,
            key='content_height_mode',
            label_visibility='visible',
        )

    with col_fullscreen:
        # Fullscreen toggle
        fullscreen = st.checkbox('⛶ Full', value=False, key='content_fullscreen', label_visibility='visible')

    # Calculate dimensions
    if width_ratio == '50:50':
        col_ratios = [1, 1]
    elif width_ratio == '40:60':
        col_ratios = [2, 3]
    elif width_ratio == '60:40':
        col_ratios = [3, 2]
    elif width_ratio == '30:70':
        col_ratios = [3, 7]
    elif width_ratio == '70:30':
        col_ratios = [7, 3]
    else:
        col_ratios = [1, 1]

    # Height mapping
    height_map = {'Small': 200, 'Medium': 400, 'Large': 600, 'XLarge': 800}
    source_height = height_map[height_mode]
    response_height = height_map[height_mode] + 100  # Response typically longer

    # Fullscreen mode: Use dialog/expander for larger view
    if fullscreen:
        source_height = 600
        response_height = 800

    # Find content columns
    source_col_1 = find_field_in_row(row, label1, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)
    source_col_2 = find_field_in_row(row, label2, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)

    response_col_1 = find_field_in_row(row, label1, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)
    response_col_2 = find_field_in_row(row, label2, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)

    # Source comparison (should be same, but show both for verification)
    if source_col_1 or source_col_2:
        st.markdown('**📄 Source Text:**')
        col1, col2 = st.columns(col_ratios)

        with col1:
            st.markdown(f'*{label1}*')
            source_1 = row.get(source_col_1, 'N/A') if source_col_1 else 'N/A'
            with st.container(height=source_height, border=True):
                st.write(source_1)

        with col2:
            st.markdown(f'*{label2}*')
            source_2 = row.get(source_col_2, 'N/A') if source_col_2 else 'N/A'
            with st.container(height=source_height, border=True):
                st.write(source_2)

        # Warn if sources differ
        if source_1 != source_2:
            st.warning('⚠️ Source texts differ between results!')

    # Response comparison (main comparison point)
    if response_col_1 or response_col_2:
        st.markdown('**📝 Response Comparison:**')

        # Get word counts if available
        wc_col_1 = response_col_1 + WORD_COUNT_SUFFIX if response_col_1 else None
        wc_col_2 = response_col_2 + WORD_COUNT_SUFFIX if response_col_2 else None

        col1, col2 = st.columns(col_ratios)

        with col1:
            wc_info = ''
            if wc_col_1 and wc_col_1 in row.index:
                wc_info = f' • {int(row[wc_col_1])} words'
            st.markdown(f'**{label1}**{wc_info}')

            response_1 = row.get(response_col_1, 'N/A') if response_col_1 else 'N/A'
            with st.container(height=response_height, border=True):
                st.write(response_1)

        with col2:
            wc_info = ''
            if wc_col_2 and wc_col_2 in row.index:
                wc_info = f' • {int(row[wc_col_2])} words'
            st.markdown(f'**{label2}**{wc_info}')

            response_2 = row.get(response_col_2, 'N/A') if response_col_2 else 'N/A'
            with st.container(height=response_height, border=True):
                st.write(response_2)

    # Fullscreen hint
    if fullscreen:
        st.caption('💡 Tip: Uncheck "Full" to return to compact view')


def render_metrics_comparison(row, label1, label2):
    """Render side-by-side metrics comparison with radar chart."""
    st.markdown('#### 📊 Metrics Comparison')

    # Extract metrics from both sides
    metrics_1 = extract_metrics_for_side(row, label1)
    metrics_2 = extract_metrics_for_side(row, label2)

    if not metrics_1['scores'] or not metrics_2['scores']:
        st.info('No metrics found')
        return

    # Radar chart comparison
    render_comparison_radar_chart(metrics_1['scores'], metrics_2['scores'], label1, label2)

    # Detailed metric-by-metric comparison
    st.markdown('**🔬 Detailed Metrics:**')

    expand_all = st.checkbox('📂 Expand all metrics', value=False, key='expand_comp_metrics')

    # Get all metric names
    all_metrics = set(metrics_1['scores'].keys()) | set(metrics_2['scores'].keys())

    for metric in sorted(all_metrics):
        render_metric_sidebyside(metric, metrics_1, metrics_2, label1, label2, expand_all)


def render_metric_sidebyside(metric, metrics_1, metrics_2, label1, label2, expanded):
    """Render side-by-side comparison for a single metric."""
    # Calculate difference
    scores_1 = metrics_1['scores'].get(metric, {})
    scores_2 = metrics_2['scores'].get(metric, {})

    # Get primary score (empty key or first available)
    score_1 = scores_1.get('', next(iter(scores_1.values()), None))
    score_2 = scores_2.get('', next(iter(scores_2.values()), None))

    diff = None
    diff_emoji = ''
    if score_1 is not None and score_2 is not None:
        diff = score_2 - score_1
        diff_emoji = f' {get_diff_emoji(diff)} ({diff:+.2f})'

    with st.expander(f'{metric.title()}{diff_emoji}', expanded=expanded):
        # Scores comparison
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f'**{label1}**')
            if scores_1:
                for model, score in sorted(scores_1.items()):
                    label = model if model else metric.title()
                    st.metric(label, f'{score:.2f} {get_score_emoji(score)}')
            else:
                st.write('N/A')

        with col2:
            st.markdown(f'**{label2}**')
            if scores_2:
                for model, score in sorted(scores_2.items()):
                    label = model if model else metric.title()
                    st.metric(label, f'{score:.2f} {get_score_emoji(score)}')
            else:
                st.write('N/A')

        # Definition (should be same, show once)
        if metric in metrics_1['definitions'] or metric in metrics_2['definitions']:
            definition = metrics_1['definitions'].get(metric) or metrics_2['definitions'].get(metric)
            if definition:
                st.caption('**Definition:**')
                st.write(definition)

        # Reasoning comparison
        reasoning_1 = metrics_1['reasoning'].get(metric, {})
        reasoning_2 = metrics_2['reasoning'].get(metric, {})

        if reasoning_1 or reasoning_2:
            st.caption('**Reasoning Comparison:**')
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f'*{label1}*')
                if reasoning_1:
                    for model, text in sorted(reasoning_1.items()):
                        if pd.notna(text) and text:
                            if model:
                                st.markdown(f'**{model}:**')
                            st.write(text)
                else:
                    st.write('N/A')

            with col2:
                st.markdown(f'*{label2}*')
                if reasoning_2:
                    for model, text in sorted(reasoning_2.items()):
                        if pd.notna(text) and text:
                            if model:
                                st.markdown(f'**{model}:**')
                            st.write(text)
                else:
                    st.write('N/A')


def render_comparison_radar_chart(scores_1, scores_2, label1, label2):
    """Render radar chart comparing two sets of scores."""
    fig = go.Figure()

    # Get common metrics
    all_metrics = set(scores_1.keys()) | set(scores_2.keys())
    metrics = sorted(all_metrics)

    # Extract scores for each side (use primary score - empty key or first)
    values_1 = []
    values_2 = []

    for metric in metrics:
        score_dict_1 = scores_1.get(metric, {})
        score_dict_2 = scores_2.get(metric, {})

        # Get primary score
        score_1 = score_dict_1.get('', next(iter(score_dict_1.values()), 0))
        score_2 = score_dict_2.get('', next(iter(score_dict_2.values()), 0))

        values_1.append(score_1)
        values_2.append(score_2)

    # Add traces
    fig.add_trace(
        go.Scatterpolar(
            r=values_1,
            theta=[m.title() for m in metrics],
            fill='toself',
            name=label1,
            line=dict(color=RADAR_COLORS['result1'], width=2),
            fillcolor=RADAR_COLORS['result1'],
            opacity=0.6,
        )
    )

    fig.add_trace(
        go.Scatterpolar(
            r=values_2,
            theta=[m.title() for m in metrics],
            fill='toself',
            name=label2,
            line=dict(color=RADAR_COLORS['result2'], width=2),
            fillcolor=RADAR_COLORS['result2'],
            opacity=0.6,
        )
    )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        showlegend=True,
        height=400,
        margin=dict(l=60, r=60, t=40, b=40),
    )

    st.plotly_chart(fig, width='stretch', key='comparison_radar')


# ============================================================================
# DATA TRANSFORMATION FOR RE-ANALYSIS
# ============================================================================


def prepare_dual_response_format(selected_rows, full_df, label1, label2):
    """
    Transform comparison data to dual-response format for re-analysis.

    Extracts:
    - source (from either side - should be same)
    - response1 (from label1)
    - response2 (from label2)
    - metadata (filename, section_id)

    Returns list of dicts ready for dual-response evaluation.
    """
    dual_data = []

    for row in selected_rows:
        # Get full row if needed
        full_row = get_full_row(row, full_df)

        # DEBUG: Print available columns to understand structure
        # st.write('Available columns:', list(full_row.index)[:10])  # First 10 columns

        # Find source columns (should be same from both sides)
        source_col_1 = find_field_in_row(full_row, label1, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)
        source_col_2 = find_field_in_row(full_row, label2, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)

        # Use first available source (they should match)
        if source_col_1 and source_col_1 in full_row.index:
            source = str(full_row[source_col_1])
        elif source_col_2 and source_col_2 in full_row.index:
            source = str(full_row[source_col_2])
        else:
            # Fallback: try to find any column with source-like keywords
            source = 'N/A'
            for col in full_row.index:
                col_lower = col.lower()
                if any(kw in col_lower for kw in SOURCE_KEYWORDS) and WORD_COUNT_SUFFIX not in col_lower:
                    if pd.notna(full_row[col]):
                        source = str(full_row[col])
                        break

        # Find response columns
        response_col_1 = find_field_in_row(full_row, label1, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)
        response_col_2 = find_field_in_row(full_row, label2, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)

        # Extract response1
        if response_col_1 and response_col_1 in full_row.index:
            response1 = str(full_row[response_col_1])
        else:
            # Fallback: find column with response keyword AND label1 suffix
            response1 = 'N/A'
            for col in full_row.index:
                if col.endswith(f'_{label1}'):
                    col_base = col.replace(f'_{label1}', '').lower()
                    if any(kw in col_base for kw in RESPONSE_KEYWORDS) and WORD_COUNT_SUFFIX not in col_base:
                        if pd.notna(full_row[col]):
                            response1 = str(full_row[col])
                            break

        # Extract response2
        if response_col_2 and response_col_2 in full_row.index:
            response2 = str(full_row[response_col_2])
        else:
            # Fallback: find column with response keyword AND label2 suffix
            response2 = 'N/A'
            for col in full_row.index:
                if col.endswith(f'_{label2}'):
                    col_base = col.replace(f'_{label2}', '').lower()
                    if any(kw in col_base for kw in RESPONSE_KEYWORDS) and WORD_COUNT_SUFFIX not in col_base:
                        if pd.notna(full_row[col]):
                            response2 = str(full_row[col])
                            break

        # Extract metadata
        join_key = full_row.get('_join_key', '')

        # Parse join key (format: filename::section_id)
        if '::' in str(join_key):
            filename, section_id = str(join_key).split('::', 1)
        else:
            filename = str(join_key)
            section_id = ''

        # Build dual-response record
        record = {
            'filename': filename,
            'section_id': section_id,
            'source': source,
            'response1': response1,
            'response2': response2,
            'label1': label1,
            'label2': label2,
        }

        # Add question if available
        question_col_1 = find_field_in_row(full_row, label1, QUESTION_FIELD_NAMES, ['question'])
        question_col_2 = find_field_in_row(full_row, label2, QUESTION_FIELD_NAMES, ['question'])

        question = None
        if question_col_1 and question_col_1 in full_row.index:
            question = full_row[question_col_1]
        elif question_col_2 and question_col_2 in full_row.index:
            question = full_row[question_col_2]

        if question and pd.notna(question) and str(question).strip() != 'N/A':
            record['question'] = str(question)

        dual_data.append(record)

    return dual_data


def get_full_row(selected_row, full_df):
    """
    Get full row from dataframe if selected_row is partial.

    For comparison dashboard, selected_row should already be complete,
    but this provides a fallback to match by _join_key.
    """
    # If selected_row is already a full row (has all columns), return it
    if isinstance(selected_row, pd.Series):
        # Try to match by _join_key if available
        if '_join_key' in selected_row.index and '_join_key' in full_df.columns:
            join_key_val = selected_row.get('_join_key')
            matches = full_df[full_df['_join_key'] == join_key_val]
            if not matches.empty:
                return matches.iloc[0]

    return selected_row


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def find_column_by_keywords(columns, keywords):
    """Find first column matching any keyword."""
    for col in columns:
        if any(kw in col.lower() for kw in keywords):
            return col
    return None


def find_field_in_row(row, label_suffix, exact_names, fuzzy_keywords):
    """Find field in row with label suffix."""
    # Try exact matches with suffix
    for name in exact_names:
        col_with_suffix = f'{name}_{label_suffix}'
        if col_with_suffix in row.index:
            return col_with_suffix

    # Try fuzzy match with suffix
    for col in row.index:
        if col.endswith(f'_{label_suffix}'):
            col_base = col.replace(f'_{label_suffix}', '')
            if any(kw in col_base.lower() for kw in fuzzy_keywords):
                if WORD_COUNT_SUFFIX not in col_base.lower():
                    return col

    return None


def extract_metrics_for_side(row, label_suffix):
    """Extract metrics data for one side of comparison."""
    scores, reasoning, definitions = {}, {}, {}

    for col in row.index:
        # Only process columns with this label suffix
        if not col.endswith(f'_{label_suffix}'):
            continue

        # Remove label suffix to get base column name
        base_col = col.replace(f'_{label_suffix}', '')
        base_col_lower = base_col.lower()

        # Definition
        if DEFINITION_SUFFIX in base_col_lower:
            metric = parse_metric_name(base_col_lower, DEFINITION_SUFFIX)
            if metric:
                definitions[metric] = row[col]

        # Score
        elif SCORE_SUFFIX in base_col_lower:
            metric = parse_metric_name(base_col_lower, SCORE_SUFFIX)
            model = parse_model_name(base_col_lower, SCORE_SUFFIX)
            if metric:
                scores.setdefault(metric, {})[model] = row[col]

        # Reasoning
        elif REASONING_SUFFIX in base_col_lower:
            metric = parse_metric_name(base_col_lower, REASONING_SUFFIX)
            model = parse_model_name(base_col_lower, REASONING_SUFFIX)
            if metric:
                reasoning.setdefault(metric, {})[model] = row[col]

    return {'scores': scores, 'reasoning': reasoning, 'definitions': definitions}


def parse_metric_name(col, suffix):
    """Parse metric name from column."""
    if suffix not in col:
        return None
    before_suffix = col.split(suffix)[0]
    return before_suffix.strip('_').split('_')[0]


def parse_model_name(col, suffix):
    """Parse model name from column."""
    if suffix not in col:
        return ''
    parts = col.split(suffix)
    return parts[1].strip('_') if len(parts) == 2 else ''


def get_score_emoji(score: float) -> str:
    """Get emoji based on score value."""
    if score >= SCORE_HIGH_THRESHOLD:
        return SCORE_EMOJI_HIGH
    if score >= SCORE_MED_THRESHOLD:
        return SCORE_EMOJI_MED
    return SCORE_EMOJI_LOW


def get_diff_emoji(diff: float) -> str:
    """Get emoji based on difference value."""
    if diff > 0.1:
        return SCORE_EMOJI_BETTER
    if diff < -0.1:
        return SCORE_EMOJI_WORSE
    return SCORE_EMOJI_SAME


def show_instructions():
    """Show instructions when no data loaded."""
    st.info(
        """
    **🔬 Side-by-Side Comparison**

    **How it works:**
    1. Upload two evaluation result files (baseline and comparison)
    2. Files are automatically joined on `filename` + `section_id`
    3. Select rows to see detailed side-by-side comparison:
       - Source and response text comparison
       - All metrics scores side-by-side
       - Reasoning explanations for each side
       - Visual difference analysis

    **Use Cases:**
    - Compare different model versions
    - Evaluate prompt changes
    - A/B test evaluation criteria
    - Track improvements across iterations
    - Validate consistency between runs

    **Requirements:**
    - Both files must have `filename` and `section_id` columns
    - Matching rows will be joined automatically
    - Unmatched rows are tracked and reported
    """
    )
