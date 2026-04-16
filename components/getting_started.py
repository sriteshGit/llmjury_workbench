# LLMJury Workbench

"""Getting Started tab - Quick guide and about information."""

import json

import streamlit as st

from __version__ import __version__


def render_getting_started_tab():
    """Render the Getting Started tab with guide and info."""
    st.header('🚀 Getting Started')

    st.info(
        '⚡ **LLMJury Workbench** - Interactive tool for running and analyzing LLM evaluations across multiple models and criteria.'
    )

    st.markdown('## 📚 Quick Start Guide')

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        st.markdown(
            """
            ### 1️⃣ Upload Data
            Upload JSON file with format:
            ```json
            {
              "id": {
                "source": "Text",
                "response": "Output"
              }
            }
            ```
            """
        )
        sample_json = {
            'example': {
                'source': 'The quick brown fox jumps over the lazy dog.',
                'response': 'A fast fox leaps above a sleepy dog.',
            }
        }
        st.download_button(
            label='📥 Download Sample',
            data=json.dumps(sample_json, indent=2),
            file_name='sample.json',
            mime='application/json',
            use_container_width=True,
        )

    with col2:
        st.markdown(
            """
            ### 2️⃣ Configure
            **Choose:**
            - Models (GPT-4o, GPT-5, Gemini)
            - Mode (metrics, question_answer, comparison)
            - Custom prompt (optional)

            💡 Use defaults for first run
            """
        )

    with col3:
        st.markdown(
            """
            ### 3️⃣ Run & Download
            1. Click **▶️ Run Evaluation**
            2. Wait for completion
            3. Download Excel/JSON results

            📊 Load in Dashboard for analysis
            """
        )

    with col4:
        st.markdown(
            """
            ### 4️⃣ Analyze Results
            **📊 Dashboard**
            - Filter & visualize data
            - Drill-down analysis
            - Export insights

            **📊 Comparison**
            - Compare multiple runs
            - Side-by-side view
            """
        )

    st.markdown('---')

    st.markdown('## 🎬 Walkthrough')

    st.info(
        'Embed a walkthrough video by editing the Getting Started tab, or follow **README.md** in the repository root.'
    )

    st.markdown('---')

    st.markdown('## ℹ️ About')

    col_a, col_b, col_c, col_d = st.columns(4)

    with col_a:
        st.metric('🤖 Models', '13+')

    with col_b:
        st.metric('📏 Criteria', '10+')

    with col_c:
        st.metric('⚡ Processing', 'Parallel')

    with col_d:
        st.metric('📥 Formats', 'Excel/JSON')

    st.markdown('### ✨ Features')

    feat_col1, feat_col2 = st.columns(2)

    with feat_col1:
        st.markdown(
            """
            **📊 Dashboard**
            - Interactive filtering & visualization
            - Export & compare results

            **🚀 Evaluation**
            - Multiple models & criteria
            - Custom prompts
            """
        )

    with feat_col2:
        st.markdown(
            """
            **📊 Comparison**
            - Side-by-side analysis
            - Performance insights

            **⚙️ Advanced**
            - Ad-hoc evaluations
            """
        )

    st.markdown('---')

    st.markdown('### 🔗 Resources')

    res_col1, res_col2 = st.columns(2)

    with res_col1:
        st.markdown('📖 **Documentation** — see `README.md` and `CODEBASE_REFERENCE.md` in the repository.')

    with res_col2:
        st.markdown('💬 **Support** — use your team’s issue tracker or internal docs for this deployment.')

    st.markdown('---')
    st.markdown(f'**Version:** {__version__} | **Stack:** Streamlit + LLMJury')
