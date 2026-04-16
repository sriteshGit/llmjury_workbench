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

"""LLMJury Workbench - Interactive evaluation and analysis tool."""

import streamlit as st
from components.comparison import render_comparison_tab
from components.evaluation_runner_unified import render_evaluation_runner_tab
from components.getting_started import render_getting_started_tab
from components.unified_dashboard import render_unified_dashboard_tab

# Page configuration
st.set_page_config(
    page_title='LLMJury Workbench',
    page_icon='⚖️',
    layout='wide',
    initial_sidebar_state='collapsed',
)

# Custom CSS for better styling
st.markdown(
    """
    <style>
    .main-header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 20px;
        padding: 1rem 0;
        margin-bottom: 2rem;
    }
    .header-title {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
    }
    .adobe-logo {
        height: 40px;
        vertical-align: middle;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .feature-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .feature-card h3 {
        color: white;
        margin-top: 0;
    }
    .info-box {
        background-color: #f8f9fa;
        border-left: 4px solid #eb1000;
        padding: 1.5rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main():
    """Main application entry point."""
    # Header with Adobe logo
    st.markdown(
        '''
        <div class="main-header">
            <img src="https://www.adobe.com/content/dam/cc/icons/Adobe_Corporate_Horizontal_Red_HEX.svg" class="adobe-logo" alt="Adobe"/>
            <span class="header-title">⚖️ LLMJury Workbench</span>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # Main tabs - Run Evaluation first as default
    tab1, tab2, tab3, tab4 = st.tabs(['🚀 Run Evaluation', '📊 Dashboard', '📊 Comparison', '📚 Getting Started'])

    with tab1:
        render_evaluation_runner_tab()

    with tab2:
        render_unified_dashboard_tab()

    with tab3:
        render_comparison_tab()

    with tab4:
        render_getting_started_tab()


if __name__ == '__main__':
    main()
