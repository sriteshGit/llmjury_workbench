# LLMJury Workbench

"""Visualization utilities for LLMJury results."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Constants
SCORE_RANGE = [0, 5.5]
DEFAULT_HEIGHT = 500
SCORE_SUFFIX = '_score'
OVERALL_SCORE = 'overall_score'


def _get_score_columns(df: pd.DataFrame, exclude_overall: bool = False) -> list[str]:
    """Helper to get score columns from DataFrame."""
    cols = [col for col in df.columns if col.endswith(SCORE_SUFFIX)]
    if exclude_overall:
        cols = [col for col in cols if col != OVERALL_SCORE]
    return cols


def _format_criteria_name(col_name: str) -> str:
    """Helper to format column name as readable criteria."""
    return col_name.replace(SCORE_SUFFIX, '').replace('_', ' ').title()


def _apply_common_layout(fig: go.Figure, title: str, yaxis_title: str = 'Score', height: int = DEFAULT_HEIGHT):
    """Apply common layout settings to figure."""
    fig.update_layout(
        title=title,
        yaxis_title=yaxis_title,
        yaxis_range=SCORE_RANGE,
        height=height,
    )


def create_score_distribution(df: pd.DataFrame, criteria: list[str]) -> go.Figure:
    """
    Create box plot for score distribution across criteria.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame
    criteria : list[str]
        List of criteria to plot

    Returns
    -------
    go.Figure
        Plotly figure
    """
    score_cols = [f'{c}{SCORE_SUFFIX}' for c in criteria if f'{c}{SCORE_SUFFIX}' in df.columns]

    if not score_cols:
        return go.Figure()

    # Melt DataFrame for plotting
    df_melted = df[score_cols].melt(var_name='Criteria', value_name='Score')
    df_melted['Criteria'] = df_melted['Criteria'].str.replace(SCORE_SUFFIX, '')

    fig = px.box(df_melted, x='Criteria', y='Score', color='Criteria', points='all')
    fig.update_layout(xaxis_title='Criteria', showlegend=False)
    _apply_common_layout(fig, 'Score Distribution by Criteria')

    return fig


def create_model_comparison(df: pd.DataFrame, criteria: str = 'overall') -> go.Figure:
    """
    Create bar chart comparing model performance.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame
    criteria : str, default='overall'
        Criteria to compare

    Returns
    -------
    go.Figure
        Plotly figure
    """
    if 'model' not in df.columns:
        return go.Figure()

    score_col = f'{criteria}{SCORE_SUFFIX}'
    if score_col not in df.columns:
        return go.Figure()

    model_avg = df.groupby('model')[score_col].mean().reset_index()
    fig = px.bar(model_avg, x='model', y=score_col, color='model', text_auto='.2f')
    fig.update_layout(xaxis_title='Model', showlegend=False)
    _apply_common_layout(fig, f'Average {criteria.title()} Score by Model', height=400)

    return fig


def create_criteria_radar(df: pd.DataFrame, section_id: str | None = None) -> go.Figure:
    """
    Create radar chart for criteria scores.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame
    section_id : str, optional
        Specific section to plot (if None, uses average)

    Returns
    -------
    go.Figure
        Plotly figure
    """
    score_cols = _get_score_columns(df, exclude_overall=True)

    if not score_cols:
        return go.Figure()

    if section_id and 'section_id' in df.columns:
        data = df[df['section_id'] == section_id].iloc[0]
        title = f'Criteria Scores for Section: {section_id}'
    else:
        data = df[score_cols].mean()
        title = 'Average Criteria Scores'

    criteria = [_format_criteria_name(col) for col in score_cols]
    scores = [data[col] for col in score_cols]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=scores, theta=criteria, fill='toself', name='Scores'))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
        showlegend=False,
        title=title,
        height=DEFAULT_HEIGHT,
    )

    return fig


def create_heatmap(df: pd.DataFrame) -> go.Figure:
    """
    Create heatmap of scores across sections and criteria.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame

    Returns
    -------
    go.Figure
        Plotly figure
    """
    score_cols = _get_score_columns(df, exclude_overall=True)

    if not score_cols or 'section_id' not in df.columns:
        return go.Figure()

    # Create pivot table
    heatmap_data = df[['section_id'] + score_cols].set_index('section_id')
    heatmap_data.columns = [col.replace(SCORE_SUFFIX, '') for col in heatmap_data.columns]

    fig = px.imshow(
        heatmap_data.T,
        title='Score Heatmap: Criteria vs Sections',
        labels=dict(x='Section', y='Criteria', color='Score'),
        color_continuous_scale='RdYlGn',
        aspect='auto',
    )
    fig.update_layout(height=max(400, len(score_cols) * 50))

    return fig


def create_comparison_chart(results_list: list[pd.DataFrame], labels: list[str]) -> go.Figure:
    """
    Create comparison chart for multiple evaluation runs.

    Parameters
    ----------
    results_list : list[pd.DataFrame]
        List of results DataFrames
    labels : list[str]
        Labels for each run

    Returns
    -------
    go.Figure
        Plotly figure
    """
    if not results_list:
        return go.Figure()

    # Get common score columns
    common_cols = set(results_list[0].columns)
    for df in results_list[1:]:
        common_cols &= set(df.columns)

    score_cols = [col for col in common_cols if col.endswith(SCORE_SUFFIX) and col != OVERALL_SCORE]

    if not score_cols:
        return go.Figure()

    # Calculate averages
    criteria = [col.replace(SCORE_SUFFIX, '') for col in score_cols]
    fig = go.Figure()

    for df, label in zip(results_list, labels):
        scores = [df[col].mean() for col in score_cols]
        fig.add_trace(go.Bar(name=label, x=criteria, y=scores))

    fig.update_layout(xaxis_title='Criteria', barmode='group')
    _apply_common_layout(fig, 'Comparison: Average Scores Across Runs', yaxis_title='Average Score')

    return fig


def create_score_trend(df: pd.DataFrame, section_col: str = 'section_id') -> go.Figure:
    """
    Create line chart showing score trends across sections.

    Parameters
    ----------
    df : pd.DataFrame
        Results DataFrame
    section_col : str, default='section_id'
        Column name for sections

    Returns
    -------
    go.Figure
        Plotly figure
    """
    if OVERALL_SCORE not in df.columns or section_col not in df.columns:
        return go.Figure()

    fig = px.line(df, x=section_col, y=OVERALL_SCORE, markers=True)
    fig.update_layout(xaxis_title='Section')
    _apply_common_layout(fig, 'Overall Score Trend Across Sections', yaxis_title='Overall Score', height=400)

    return fig
