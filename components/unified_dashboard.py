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
Unified dashboard combining results viewing and detailed analysis.

Framework-agnostic design:
- Uses patterns from LLMJury constants (SCORE_SUFFIX, REASONING_SUFFIX)
- Field detection from field_mappings (PROMPT_FIELD_NAMES, ANSWER_FIELD_NAMES)
- No hardcoded strings - adapts to framework changes automatically
"""

from io import BytesIO
from pathlib import Path

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

# Patterns
DEFINITION_SUFFIX = '_definition'
WORD_COUNT_SUFFIX = '_word_count'

# Source keywords for fuzzy matching
SOURCE_KEYWORDS = ['source', 'prompt', 'context', 'ground_truth', 'reference', 'question']
RESPONSE_KEYWORDS = ['response', 'answer', 'summary', 'output', 'result', 'prediction']

# Score thresholds and colors
SCORE_HIGH_THRESHOLD = 4.0
SCORE_MED_THRESHOLD = 3.0
SCORE_EMOJI_HIGH = '🟢'
SCORE_EMOJI_MED = '🟡'
SCORE_EMOJI_LOW = '🔴'
RADAR_CHART_COLORS = [
    '#ffc658',
    '#9b59b6',
    '#8884d8',
    '#82ca9d',
    '#3498db',
    '#e74c3c',
    '#f39c12',
    '#2ecc71',
]


def get_score_emoji(score: float) -> str:
    """Get emoji based on score value."""
    if score >= SCORE_HIGH_THRESHOLD:
        return SCORE_EMOJI_HIGH
    if score >= SCORE_MED_THRESHOLD:
        return SCORE_EMOJI_MED
    return SCORE_EMOJI_LOW


def render_unified_dashboard_tab():
    """Main dashboard rendering function."""
    st.header('📊 LLM Jury Analysis Dashboard')
    st.markdown('Comprehensive evaluation analysis with filtering and drill-down')

    data = load_data_section()
    if data is None:
        st.info('👆 Upload evaluation results (JSON or Excel) to begin analysis')
        return

    df, sheet_name = prepare_dataframe(data)
    if df.empty:
        st.warning('No data in selected sheet')
        return

    # Full data view
    with st.expander('🔍 View Full Data Table', expanded=False):
        st.dataframe(df, width='stretch', height=400)

    score_cols = get_score_columns(df.columns)
    (
        search_term,
        filter_col,
        min_score,
        max_score,
        sort_by,
        sort_order,
        file_section_selected,
        file_col,
        section_col,
        high_threshold,
        med_threshold,
    ) = render_filters(df, score_cols)

    # Apply filters
    filtered_df = apply_filters(
        df,
        search_term,
        filter_col,
        min_score,
        max_score,
        sort_by,
        sort_order,
        file_section_selected,
        file_col,
        section_col,
    )

    # Dataset stats
    show_dataset_stats(df, sheet_name, filtered_df)

    # Data grid
    display_cols = select_display_columns(filtered_df, sheet_name)
    if not display_cols:
        st.warning('Select at least one column')
        return

    # Grid display with instructions
    st.markdown('**✨ Select rows for analysis**')
    st.caption(
        '💡 Use the checkbox in the header to select/deselect all | '
        'Click 📊 columns button (top right) to show/hide columns | Drag edges to resize'
    )

    # Display grid with all rows pre-selected by default
    selected_rows = display_data_grid(filtered_df, display_cols, high_threshold, med_threshold, pre_select_all=True)

    # Detailed view - adaptive based on number of selections
    if selected_rows:
        render_multi_row_analysis(selected_rows, filtered_df)

        # Export selected rows in multiple formats
        st.markdown('---')
        st.caption(f'**📥 Export {len(selected_rows)} selected row{"s" if len(selected_rows) > 1 else ""}:**')

        # Convert selected rows to DataFrame for export
        selected_df = pd.DataFrame(selected_rows)

        # Prepare Excel export
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            selected_df.to_excel(writer, index=False, sheet_name='selected_data')
        excel_buffer.seek(0)

        # Prepare JSON export
        json_data = selected_df.to_json(orient='records', indent=2)

        # Download buttons in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                '📊 Excel (.xlsx)',
                excel_buffer.getvalue(),
                'llmjury_selected.xlsx',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='export_excel',
                width='stretch',
            )
        with col2:
            st.download_button(
                '📋 JSON (.json)',
                json_data,
                'llmjury_selected.json',
                'application/json',
                key='export_json',
                width='stretch',
            )
        with col3:
            if st.button(
                '🔄 Re-analyze',
                key='goto_reanalysis',
                help='Go to Run Evaluation tab to re-analyze selected rows',
                type='secondary',
                width='stretch',
            ):
                # Store selected rows in session state for re-analysis ONLY when button is clicked
                st.session_state['export_data'] = selected_df.to_dict('records')
                st.session_state['reanalysis_clicked'] = True
                st.session_state['auto_run_ready'] = True  # Flag for auto-run readiness

        # Show message after buttons (outside columns for uniform layout)
        if st.session_state.get('reanalysis_clicked', False):
            st.info('✅ Data ready! Switch to **🚀 Run Evaluation** tab.')
            st.balloons()
            st.session_state['reanalysis_clicked'] = False


def prepare_dataframe(data):
    """Prepare DataFrame with sheet selection."""
    if isinstance(data, dict) and 'data' not in data:
        sheet_names = list(data.keys())
        default_sheet = SheetName.JURY_RESULTS.value if SheetName.JURY_RESULTS.value in sheet_names else sheet_names[0]
        default_idx = sheet_names.index(default_sheet)

        if len(sheet_names) > 1:
            sheet_name = st.selectbox('📑 Select Sheet', sheet_names, index=default_idx, key='sheet_sel')
            return data[sheet_name], sheet_name
        return data[sheet_names[0]], sheet_names[0]

    df = pd.DataFrame(data.get('data', data)) if isinstance(data, dict) else pd.DataFrame(data)
    return df, 'JSON Data' if isinstance(data, dict) else 'Uploaded Data'


def show_dataset_stats(df, sheet_name, filtered_df):
    """Show dataset statistics."""
    cols = st.columns(4)
    cols[0].metric('Rows', len(df))
    cols[1].metric('Columns', len(df.columns))
    cols[2].metric('Filtered Rows', len(filtered_df))
    score_cols = get_score_columns(df.columns)
    cols[3].metric('Score Columns', len(score_cols))


def find_column_by_keyword(columns, keywords):
    """Find first column matching any keyword."""
    for col in columns:
        if any(kw in col.lower() for kw in keywords):
            return col
    return None


def get_score_columns(columns):
    """Get all score columns."""
    return [c for c in columns if SCORE_SUFFIX in c]


def render_filters(df, score_cols):
    """Render filter controls."""
    with st.expander('🔍 Filters & Search', expanded=True):
        # # File + Section filter
        # Search and score filters
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            # File + Section filter with built-in search
            file_col = find_column_by_keyword(df.columns, ['filename', 'file'])
            section_col = find_column_by_keyword(df.columns, ['section'])
            file_section_selected = []

            if file_col and section_col:
                filter_keys = df[file_col].astype(str) + ' :: ' + df[section_col].astype(str)
                unique_keys = sorted(filter_keys.unique())

                if len(unique_keys) > 1:
                    # Combined search + filter in single multiselect (has built-in search)
                    file_section_selected = st.multiselect(
                        f'📂 Filter by File :: Section ({len(unique_keys)} total)',
                        options=unique_keys,
                        default=[],
                        key='file_section_filter_v2',
                        placeholder='🔍 Type to search and select...',
                        help='Start typing to filter the list, then select one or more entries',
                    )

            search_term = st.text_input('🔎 Search by Text', '', key='search', placeholder='Search in content...')

        with col2:
            # Metric selection dropdown
            filter_col = st.selectbox('Filter by Metric', score_cols, key='metric_filter') if score_cols else None
            min_val, max_val = (
                st.slider('Score Range', 0.0, 5.0, (0.0, 5.0), step=0.1, key='score_range')
                if score_cols
                else (0.0, 5.0)
            )

        with col3:
            sort_opts = ['index']
            if section_col:
                sort_opts.append(section_col)
            sort_opts.extend(score_cols[:5])

            sort_by = st.selectbox('Sort', sort_opts, key='sort')
            sort_order = st.radio('Order', ['Asc', 'Desc'], horizontal=True, key='order')

        # Color threshold settings
        st.markdown('**🎨 Grid Color Thresholds:**')
        thresh_col1, thresh_col2, thresh_col3 = st.columns(3)
        with thresh_col1:
            high_threshold = st.number_input(
                '🟢 Good ≥', min_value=0.0, max_value=5.0, value=4.0, step=0.1, key='high_thresh'
            )
        with thresh_col2:
            med_threshold = st.number_input(
                '🟡 Acceptable ≥',
                min_value=0.0,
                max_value=5.0,
                value=3.0,
                step=0.1,
                key='med_thresh',
            )
        with thresh_col3:
            st.number_input('🔴 Bad <', value=med_threshold, disabled=True, key='bad_thresh_display')

    return (
        search_term,
        filter_col,
        min_val,
        max_val,
        sort_by,
        sort_order,
        file_section_selected,
        file_col,
        section_col,
        high_threshold,
        med_threshold,
    )


def apply_filters(
    df,
    search_term,
    filter_col,
    min_score,
    max_score,
    sort_by,
    sort_order,
    file_section_selected,
    file_col,
    section_col,
):
    """Apply all filters."""
    result = df.copy()

    # File + Section filter
    if file_section_selected and file_col and section_col:
        filter_keys = result[file_col].astype(str) + ' :: ' + result[section_col].astype(str)
        result = result[filter_keys.isin(file_section_selected)]

    # Search
    if search_term:
        result = result[result.apply(lambda r: search_term.lower() in str(r).lower(), axis=1)]

    # Score filter
    if filter_col and filter_col in result.columns:
        result = result[(result[filter_col] >= min_score) & (result[filter_col] <= max_score)]

    # Sort
    if sort_by != 'index' and sort_by in result.columns:
        result = result.sort_values(sort_by, ascending=(sort_order == 'Asc'))

    return result


def select_display_columns(df, sheet_name):
    """Column selection with toggles and smart grouping."""
    all_cols = list(df.columns)
    st.markdown('**Column Management:**')

    # Quick filter buttons
    col1, col2, col3, col4 = st.columns(4)

    # Use single source of truth: widget_key
    # state_key is only for tracking button actions
    widget_key = f'cols_widget_{sheet_name}'
    init_key = f'cols_initialized_{sheet_name}'

    # Initialize on first load ONLY
    if init_key not in st.session_state:
        if sheet_name == SheetName.JURY_RESULTS.value:
            default_cols = all_cols  # jury_results: all columns
        else:
            default_cols = get_mandatory_columns(all_cols)  # others: suggested columns

        st.session_state[widget_key] = default_cols
        st.session_state[init_key] = True

    # CRITICAL: Always filter widget state to only valid columns
    # This prevents 'value not in options' errors when data changes
    if widget_key in st.session_state:
        st.session_state[widget_key] = [c for c in st.session_state[widget_key] if c in all_cols]

    # Button actions - directly update widget state
    if col1.button('✅ All', key=f'all_{sheet_name}'):
        st.session_state[widget_key] = all_cols
        st.rerun()
    if col2.button('🎯 Scores Only', key=f'scores_{sheet_name}'):
        st.session_state[widget_key] = [
            c for c in all_cols if '_score' in c.lower() or any(kw in c.lower() for kw in ['filename', 'section'])
        ]
        st.rerun()
    if col3.button('📝 + Text', key=f'text_{sheet_name}'):
        st.session_state[widget_key] = [
            c
            for c in all_cols
            if '_score' in c.lower() or any(kw in c.lower() for kw in ['filename', 'section', 'source', 'response'])
        ]
        st.rerun()
    if col4.button('❌ Clear', key=f'clear_{sheet_name}'):
        st.session_state[widget_key] = []
        st.rerun()

    # Show column count (use widget_key as single source of truth)
    current_selection = st.session_state.get(widget_key, [])
    st.caption(f'Selected: {len(current_selection)} of {len(all_cols)} columns')

    # Multiselect - key IS the state, no separate default needed
    # Streamlit will use st.session_state[widget_key] as the value automatically
    selected = st.multiselect(
        'Selected columns',
        all_cols,
        key=widget_key,  # This makes st.session_state[widget_key] the source of truth
    )

    return selected


def get_mandatory_columns(columns):
    """Get mandatory columns dynamically."""
    mandatory = []

    # Identifiers
    for col in columns:
        if any(kw in col.lower() for kw in ['filename', 'file', 'section']):
            if col not in mandatory:
                mandatory.append(col)

    # Source/response
    source_col = find_field(columns, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)
    if source_col:
        mandatory.append(source_col)

    response_col = find_field(columns, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)
    if response_col:
        mandatory.append(response_col)

    # All scores
    mandatory.extend(get_score_columns(columns))

    return list(dict.fromkeys(mandatory))  # Remove duplicates, preserve order


def find_field(columns, exact_names, fuzzy_keywords):
    """Find field by exact name or fuzzy keyword match."""
    # Exact match
    for name in exact_names:
        if name in columns:
            return name

    # Fuzzy match
    for col in columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in fuzzy_keywords):
            if WORD_COUNT_SUFFIX not in col_lower:
                return col

    return None


def display_data_grid(filtered_df, display_cols, high_threshold, med_threshold, pre_select_all=True):
    """Display grid and handle selection - returns list of selected rows."""
    if is_aggrid_available():
        # Auto-detect columns to pin
        pinned = [c for c in display_cols if any(kw in c.lower() for kw in ['filename', 'section'])][:2]

        grid = display_aggrid(
            filtered_df[display_cols].reset_index(drop=True),
            height=400,
            theme='streamlit',
            pinned_cols=pinned,
            fit_columns=False,
            score_thresholds=(high_threshold, med_threshold),
            pre_select_all=pre_select_all,
        )
        selected = grid.get('selected_rows', [])

        # Return list of selected rows - if nothing selected but pre_select_all is True, return all
        if selected is not None and len(selected) > 0:
            if isinstance(selected, pd.DataFrame):
                return [selected.iloc[i] for i in range(len(selected))]
            return [pd.Series(row) if isinstance(row, dict) else row for row in selected]
        elif pre_select_all:
            # If pre-select all is enabled and no explicit selection, return all rows
            return [filtered_df[display_cols].iloc[i] for i in range(len(filtered_df))]
    else:
        st.dataframe(filtered_df[display_cols], width='stretch', height=400)
        idx = st.number_input('Row index', 0, len(filtered_df) - 1, 0, key='idx')
        return [filtered_df.iloc[idx]]

    return []


def render_multi_row_analysis(selected_rows, full_df):
    """Multi-row analysis with aggregate stats and detailed view selector."""
    num_selected = len(selected_rows)

    # Subtle header
    st.caption(f'📊 {num_selected} row{"s" if num_selected > 1 else ""} selected')

    # Show aggregate statistics (collapsed by default)
    render_aggregate_stats(selected_rows, full_df)

    # Build options with filename :: section format
    options = []
    for i, row in enumerate(selected_rows):
        file_col = find_column_by_keyword(row.index, ['filename', 'file'])
        section_col = find_column_by_keyword(row.index, ['section'])

        filename = row.get(file_col, '') if file_col else ''
        section = row.get(section_col, '') if section_col else ''

        if filename and section:
            label = f'{filename} :: {section}'
        elif filename:
            label = filename
        elif section:
            label = section
        else:
            label = f'Row {i+1}'

        options.append(label)

    # Combined search + select for detailed view
    st.markdown('**🔍 Detailed view:**')

    # Use selectbox with direct options for simpler UX
    selected_option = st.selectbox(
        'Select a row to view details',
        options=options,
        key='row_selector',
        help='🔍 Start typing to search through selected rows',
        label_visibility='collapsed',
    )

    # Find the index of the selected option
    if selected_option:
        selected_idx = options.index(selected_option)
        render_detailed_view(selected_rows[selected_idx], full_df)


def render_detailed_view(selected_row, full_df, compact=False):
    """Render detailed analysis for selected row."""
    # Get full row from original df if selected_row only has subset
    full_row = get_full_row(selected_row, full_df)

    # Generate unique ID for this row
    section_col = find_column_by_keyword(full_row.index, ['section'])
    row_id = (
        str(full_row.get(section_col, hash(str(full_row.to_dict()))))[:20]
        if section_col
        else str(hash(str(full_row.to_dict())))[:20]
    )

    # Content
    render_content_section(full_row)

    # Metrics
    metrics_data = extract_metrics_data(full_row)
    if metrics_data['scores']:
        render_metrics_section(metrics_data, row_id)


def render_aggregate_stats(selected_rows, full_df):
    """Show aggregate statistics for ALL jury score columns across selected rows."""
    # Create DataFrame from selected rows first
    selected_df = pd.DataFrame([get_full_row(row, full_df) for row in selected_rows])

    # Get all score columns from the selected DataFrame
    score_cols = [col for col in selected_df.columns if SCORE_SUFFIX in col]

    if not score_cols:
        st.info('No score columns found in selected rows')
        return

    # Calculate stats for each score column
    stats_data = []
    for col in score_cols:
        values = selected_df[col].dropna()
        if len(values) > 0:
            stats_data.append(
                {
                    'Metric': col,  # Keep full column name for clarity
                    'Avg': values.mean(),
                    'Min': values.min(),
                    'Max': values.max(),
                    'Std': values.std() if len(values) > 1 else 0,
                    'Count': len(values),
                }
            )

    # Show statistics table in expandable (collapsed by default)
    if stats_data:
        with st.expander(f'📊 {len(stats_data)} metrics • {len(selected_rows)} rows', expanded=False):
            stats_df = pd.DataFrame(stats_data)
            st.dataframe(
                stats_df.style.format(
                    {
                        'Avg': '{:.2f}',
                        'Min': '{:.2f}',
                        'Max': '{:.2f}',
                        'Std': '{:.2f}',
                        'Count': '{:.0f}',
                    }
                ).background_gradient(subset=['Avg'], cmap='RdYlGn', vmin=0, vmax=5),
                width='stretch',
                height=min(450, len(stats_data) * 35 + 50),
            )


def get_full_row(selected_row, full_df):
    """Get full row from dataframe if selected_row is partial."""
    # Try to match by section_id
    section_col = find_column_by_keyword(selected_row.index, ['section'])
    if section_col and section_col in full_df.columns:
        section_val = selected_row.get(section_col)
        matches = full_df[full_df[section_col] == section_val]
        if not matches.empty:
            return matches.iloc[0]

    return selected_row


def render_content_section(row):
    """Render source and response in side-by-side comparison view."""
    # Get content and word counts
    source = find_field_value(row, PROMPT_FIELD_NAMES + QUESTION_FIELD_NAMES, SOURCE_KEYWORDS)
    response = find_field_value(row, ANSWER_FIELD_NAMES, RESPONSE_KEYWORDS)

    source_wc = next(
        (c for c in row.index if c.endswith(WORD_COUNT_SUFFIX) and any(kw in c.lower() for kw in SOURCE_KEYWORDS)),
        None,
    )
    response_wc = next(
        (c for c in row.index if c.endswith(WORD_COUNT_SUFFIX) and any(kw in c.lower() for kw in RESPONSE_KEYWORDS)),
        None,
    )

    # Generate unique key for this row
    section_col = find_column_by_keyword(row.index, ['section'])
    row_id = (
        str(row.get(section_col, hash(str(row.to_dict()))))[:20] if section_col else str(hash(str(row.to_dict())))[:20]
    )

    # Expansion toggle
    expanded = st.checkbox('⛶', value=False, key=f'expand_{row_id}', label_visibility='visible')

    height = 450 if expanded else 200

    # Side-by-side columns
    col1, col2 = st.columns(2, gap='small')

    with col1:
        st.markdown('**📄 Source**' + (f' • {int(row[source_wc])} words' if source_wc else ''))
        with st.container(height=height, border=True):
            st.write(source)

    with col2:
        wc_info = f' • {int(row[response_wc])} words' if response_wc else ''
        if response_wc and source_wc and row[source_wc] > 0:
            compression_pct = int(row[response_wc]) / int(row[source_wc]) * 100
            wc_info = f' • {int(row[response_wc])} words ({compression_pct:.1f}%)'
        st.markdown('**📝 Response**' + wc_info)
        with st.container(height=height, border=True):
            st.write(response)

    # Also display 'Question' field below side-by-side view, if available
    question = find_field_value(row, QUESTION_FIELD_NAMES, ['question'])
    if question and question != 'N/A':
        st.markdown('**❓ Question:**')
        st.info(question)


def find_field_value(row, exact_names, fuzzy_keywords):
    """Find field value by exact or fuzzy match."""
    # Exact match
    for name in exact_names:
        if name in row.index and pd.notna(row.get(name)):
            return str(row[name])

    # Fuzzy match
    for col in row.index:
        if any(kw in col.lower() for kw in fuzzy_keywords):
            if WORD_COUNT_SUFFIX not in col.lower() and pd.notna(row.get(col)):
                return str(row[col])

    return 'N/A'


def render_metrics_section(metrics_data, row_id=None):
    """Render metrics analysis section."""
    st.divider()

    # Header with expand all toggle
    col_title, col_toggle = st.columns([4, 1])
    with col_title:
        st.markdown('**📊 Metrics**')
    with col_toggle:
        expand_key = f'expand_all_metrics_{row_id}' if row_id else 'expand_all_metrics'
        expand_all = st.checkbox('📂 Expand all', value=False, key=expand_key)

    # Radar chart - more compact
    render_radar_chart(metrics_data['scores'], row_id)

    # Detailed breakdown in expanders
    for metric in sorted(metrics_data['scores'].keys()):
        with st.expander(f'{metric.title()}', expanded=expand_all):
            render_metric_detail(metric, metrics_data)


def render_metric_detail(metric, metrics_data):
    """Render details for a single metric."""
    # Scores - compact layout
    models = metrics_data['scores'][metric]
    cols = st.columns(len(models))
    for idx, (model, score) in enumerate(sorted(models.items())):
        with cols[idx]:
            label = model if model else metric.title()
            st.metric(label, f'{score:.2f} {get_score_emoji(score)}', label_visibility='visible')

    # Definition - compact
    if metric in metrics_data['definitions']:
        st.caption('**Definition**')
        st.write(metrics_data['definitions'][metric])

    # Reasoning - compact
    if metric in metrics_data['reasoning']:
        st.caption('**Reasoning**')
        for model, reasoning in sorted(metrics_data['reasoning'][metric].items()):
            if pd.notna(reasoning) and reasoning:
                if model:
                    st.markdown(f'*{model}:*')
                st.write(reasoning)


def extract_metrics_data(row):
    """Extract scores, reasoning, definitions using patterns."""
    scores, reasoning, definitions = {}, {}, {}

    for col in row.index:
        col_lower = col.lower()

        # Definition
        if DEFINITION_SUFFIX in col_lower:
            metric = parse_metric_name(col_lower, DEFINITION_SUFFIX)
            if metric:
                definitions[metric] = row[col]

        # Score
        elif SCORE_SUFFIX in col_lower:
            metric = parse_metric_name(col_lower, SCORE_SUFFIX)
            model = parse_model_name(col_lower, SCORE_SUFFIX)
            if metric:
                scores.setdefault(metric, {})[model] = row[col]

        # Reasoning
        elif REASONING_SUFFIX in col_lower:
            metric = parse_metric_name(col_lower, REASONING_SUFFIX)
            model = parse_model_name(col_lower, REASONING_SUFFIX)
            if metric:
                reasoning.setdefault(metric, {})[model] = row[col]

    return {'scores': scores, 'reasoning': reasoning, 'definitions': definitions}


def parse_metric_name(col, suffix):
    """Parse metric name from column (e.g., 'accuracy_score_jury' -> 'accuracy')."""
    if suffix not in col:
        return None
    # Get everything before suffix, take first part before underscore
    before_suffix = col.split(suffix)[0]
    return before_suffix.strip('_').split('_')[0]


def parse_model_name(col, suffix):
    """Parse model name from column (e.g., 'accuracy_score_jury' -> 'jury')."""
    if suffix not in col:
        return ''
    parts = col.split(suffix)
    return parts[1].strip('_') if len(parts) == 2 else ''


def render_radar_chart(score_data, row_id=None):
    """Render radar chart."""
    fig = go.Figure()

    all_models = set()
    for metric_scores in score_data.values():
        all_models.update(metric_scores.keys())

    # Assign colors to models
    model_colors = {m: RADAR_CHART_COLORS[i % len(RADAR_CHART_COLORS)] for i, m in enumerate(sorted(all_models))}

    for model in sorted(all_models):
        metrics, scores = [], []
        for metric, model_scores in sorted(score_data.items()):
            if model in model_scores:
                metrics.append(metric.title())
                scores.append(model_scores[model])

        if metrics:
            name = model if model else 'Score'
            fig.add_trace(
                go.Scatterpolar(
                    r=scores,
                    theta=metrics,
                    fill='toself',
                    name=name,
                    line=dict(color=model_colors.get(model, '#999'), width=2),
                    fillcolor=model_colors.get(model, '#999'),
                    opacity=0.6,
                    text=[f'{s:.2f}' for s in scores],
                    textposition='top center',
                    textfont=dict(size=10),
                    mode='lines+markers+text',
                    hovertemplate='<b>%{theta}</b><br>Score: %{r:.2f}<extra></extra>',
                )
            )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        showlegend=True,
        height=350,
        margin=dict(l=40, r=40, t=20, b=20),
    )

    chart_key = f'radar_{row_id}' if row_id else 'radar'
    st.plotly_chart(fig, width='stretch', key=chart_key)


def load_data_section():
    """Load data from session or upload."""

    # Check if data was loaded from evaluation runner
    if 'dashboard_data' in st.session_state and st.session_state.dashboard_data:
        col1, col2 = st.columns([3, 1])
        filename = st.session_state.get('dashboard_filename', 'Evaluation Results')
        col1.success(f'✅ Loaded from evaluation: {filename}')
        if col2.button('🔄 Clear', key='clear_dashboard'):
            del st.session_state.dashboard_data
            if 'dashboard_filename' in st.session_state:
                del st.session_state.dashboard_filename
            st.rerun()
        return st.session_state.dashboard_data

    # File upload (supports file paths too!)
    st.markdown('**📤 Upload Results:**')
    col_upload, col_path = st.columns([3, 1])

    with col_upload:
        uploaded = st.file_uploader('Upload file', type=['json', 'xlsx'], key='upload', label_visibility='collapsed')
        if uploaded:
            ext = uploaded.name.split('.')[-1]
            return load_results(uploaded) if ext == 'json' else load_excel_all_sheets(uploaded)

    with col_path:
        file_path_input = st.text_input(
            'File path',
            key='file_path_input',
            label_visibility='collapsed',
            placeholder='Paste file path here: /path/to/results.xlsx',
        )
        if file_path_input and st.button('📂 Load', key='load_from_path'):
            try:
                file_path = Path(file_path_input.strip())
                if file_path.exists():
                    if file_path.suffix == '.xlsx':
                        data = load_excel_all_sheets(str(file_path))
                        st.session_state['dashboard_data'] = data
                        st.session_state['dashboard_filename'] = file_path.name
                        st.rerun()
                    elif file_path.suffix == '.json':
                        data = load_results(file_path=str(file_path))
                        st.session_state['dashboard_data'] = data
                        st.session_state['dashboard_filename'] = file_path.name
                        st.rerun()
                else:
                    st.error('File not found!')
            except Exception as e:
                st.error(f'Error loading file: {e}')

    return None
