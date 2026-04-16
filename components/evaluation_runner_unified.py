# LLMJury Workbench

"""Unified evaluation runner for LLMJury Workbench - handles both fresh and re-analysis."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from llmjury.env_bootstrap import load_llmjury_env

load_llmjury_env()

import streamlit as st
from utils.data_converter import convert_dashboard_export_to_eval_format
from utils.data_loader import load_excel_all_sheets

from llmjury.constants import EvaluationCriteria, EvaluationMode


def _cleanup_old_files(directory, days=7):
    """Remove files older than specified days."""
    try:
        cutoff = time.time() - (days * 86400)
        for f in Path(directory).iterdir():
            if f.is_file() and not f.name.startswith('.') and f.stat().st_mtime < cutoff:
                f.unlink()
    except Exception:
        pass


def _create_adhoc_eval_data(source, response, question=None, response2=None, additional_data_str=None):
    """Create evaluation data from ad-hoc text inputs."""
    # Create the evaluation entry with required fields
    eval_entry = {'source': source.strip(), 'response': response.strip()}

    # Add optional top-level fields
    if question and question.strip():
        eval_entry['question'] = question.strip()

    if response2 and response2.strip():
        eval_entry['response2'] = response2.strip()

    # Parse and add additional_data if provided
    if additional_data_str and additional_data_str.strip():
        try:
            parsed_additional = json.loads(additional_data_str.strip())
            if isinstance(parsed_additional, dict):
                eval_entry['additional_data'] = parsed_additional
            else:
                eval_entry['additional_data'] = {'custom_data': str(parsed_additional)}
        except json.JSONDecodeError:
            # If not valid JSON, store as string in additional_data
            eval_entry['additional_data'] = {'custom_data': additional_data_str.strip()}

    # Return in LLMJury format: {key: {source, response, question, response2, additional_data}}
    return {'adhoc_entry': eval_entry}


def render_evaluation_runner_tab():
    """Unified evaluation runner for fresh evaluation and re-analysis."""
    st.header('🚀 Run LLMJury Evaluation')

    # Data loading section
    data, needs_conversion = _load_evaluation_data_unified()
    if not data:
        return

    st.markdown('---')

    # Configuration section
    config = _get_evaluation_config(needs_conversion)

    # Handle conversion if triggered (from Input Data section)
    if needs_conversion and st.session_state.get('trigger_conversion', False):
        output_dir = Path(config['output_path'])
        output_dir.mkdir(parents=True, exist_ok=True)
        _convert_and_save_data(data, config, output_dir)
        st.session_state['trigger_conversion'] = False
        st.rerun()

    st.markdown('---')

    # Run evaluation
    _run_evaluation_section(data, config, needs_conversion)


def _load_evaluation_data_unified():
    """Unified data loading - handles dashboard data, file upload, and ad-hoc input."""
    st.subheader('📁 Input Data')

    # Create tabs for different input methods - Upload JSON first as default
    tab_upload, tab_dashboard, tab_adhoc = st.tabs(['📤 Upload JSON', '📊 Dashboard Data', '✏️ Ad-hoc Input'])

    # Track which tab has data
    data = None
    needs_conversion = False

    # Tab 1: Dashboard Data
    with tab_dashboard:
        # Check for both types of dashboard data
        has_single_response = 'export_data' in st.session_state and st.session_state.export_data
        has_dual_response = 'dual_response_data' in st.session_state and st.session_state.dual_response_data

        if has_dual_response:
            # Dual-response data from comparison dashboard
            st.success(f'✅ {len(st.session_state.dual_response_data)} dual-response items from comparison dashboard')
            st.info('💡 This data contains both responses (a & b) for side-by-side evaluation')

            use_dual_data = st.checkbox(
                '🔄 Use this dual-response data',
                value=True,
                key='use_dual_response_data',
                help='Evaluate both responses side-by-side',
            )

            if use_dual_data:
                with st.expander('📋 Preview dual-response data'):
                    sample = st.session_state.dual_response_data[0]
                    st.json(sample)
                    st.caption(
                        f'Format: source (shared), '
                        f'response1 (label: {sample.get("label1", "a")}), '
                        f'response2 (label: {sample.get("label2", "b")})'
                    )

                # Dual-response data is already in correct format (source, response1, response2)
                # No conversion needed - it's ready to use
                st.success('✅ Dual-response data is ready for evaluation')
                st.caption('💡 Evaluation will run on both responses and create comparison results')

                data = st.session_state.dual_response_data
                needs_conversion = False  # Dual-response data is already in correct format
                st.session_state['data_source'] = 'Dual-Response'
                st.session_state['is_dual_response'] = True

        elif has_single_response:
            # Single-response data from unified dashboard
            st.success(f'✅ {len(st.session_state.export_data)} rows from dashboard')
            use_dashboard_data = st.checkbox(
                '📊 Use this dashboard data',
                value=True,
                key='use_dashboard_data',
                help='Use data exported from dashboard',
            )

            if use_dashboard_data:
                with st.expander('📋 Preview dashboard data'):
                    st.json(st.session_state.export_data[0])

                # Inline conversion section
                st.caption('📋 Dashboard data needs to be converted to LLMJury format before evaluation')

                # Show conversion results if already converted
                if 'converted_data_path' in st.session_state:
                    st.success(f'✅ Converted {st.session_state.get("converted_count", "?")} entries')
                    st.info(f'📁 Saved to: `{Path(st.session_state["converted_data_path"]).parent}`')

                    with st.expander('📋 Preview Converted Data'):
                        converted_file = Path(st.session_state['converted_data_path'])
                        if converted_file.exists():
                            with open(converted_file, encoding='utf-8') as f:
                                converted = json.load(f)
                                first_key = list(converted.keys())[0]
                                st.json({first_key: converted[first_key]})
                                st.caption('Format: `{filename_sectionid: {source, response, additional_data}}`')
                else:
                    # Conversion button
                    if st.button(
                        '🔄 Convert & Save',
                        type='secondary',
                        width='stretch',
                        key='convert_dashboard',
                    ):
                        st.session_state['trigger_conversion'] = True
                        st.rerun()

                data = st.session_state.export_data
                needs_conversion = True
                st.session_state['data_source'] = 'Dashboard'
                st.session_state['is_dual_response'] = False

        else:
            st.info('💡 No dashboard data available')
            st.caption('Export data from Dashboard or Comparison tabs to use here')

    # Tab 2: Upload JSON
    with tab_upload:
        st.info('💡 Upload JSON file(s) or specify a folder path')

        # Sample JSON and Format Documentation
        col_info, col_sample = st.columns([3, 1])

        with col_info:
            with st.expander('📖 Expected JSON Format', expanded=False):
                st.markdown(
                    """
                    **LLMJury expects a dictionary with the following structure:**

                    ```json
                    {
                      "unique_key_1": {
                        "source": "Original text or context",
                        "response": "Generated response to evaluate",
                        "question": "Optional question (for Q&A mode)",
                        "response2": "Optional second response (for comparison)",
                        "additional_data": {
                          "custom_field": "Any additional metadata"
                        }
                      },
                      "unique_key_2": { ... }
                    }
                    ```

                    **Required Fields:**
                    - `source`: The original/reference text
                    - `response`: The text to be evaluated

                    **Optional Fields:**
                    - `question`: For Q&A evaluation mode
                    - `response2`: For comparison mode
                    - `additional_data`: Custom metadata (dict)
                    """
                )

        with col_sample:
            # Sample JSON download button
            sample_json = {
                'example_1': {
                    'source': 'The quick brown fox jumps over the lazy dog.',
                    'response': 'A fast, brown-colored fox leaps above a sleepy canine.',
                    'question': 'Paraphrase the sentence',
                    'additional_data': {'category': 'paraphrasing', 'difficulty': 'easy'},
                },
                'example_2': {
                    'source': 'Artificial intelligence is transforming various industries.',
                    'response': (
                        'AI technology is revolutionizing multiple sectors including '
                        'healthcare, finance, and transportation.'
                    ),
                    'additional_data': {'category': 'expansion'},
                },
            }

            st.download_button(
                label='📥 Download Sample',
                data=json.dumps(sample_json, indent=2),
                file_name='llmjury_sample.json',
                mime='application/json',
                help='Download a sample JSON file to see the expected format',
                use_container_width=True,
            )

        # Two options: upload files or use folder path
        upload_method = st.radio(
            'Input Method',
            ['📤 Upload Files', '📁 Folder Path'],
            horizontal=True,
            key='upload_method',
        )

        if upload_method == '📤 Upload Files':
            # Multiple file uploader
            uploaded_files = st.file_uploader(
                '📤 Upload JSON file(s)',
                type=['json'],
                accept_multiple_files=True,
                help='Upload one or more JSON files in LLMJury format',
                key='upload_eval_json',
            )

            if uploaded_files:
                try:
                    # Load all files
                    all_data = {}
                    total_entries = 0

                    for uploaded_file in uploaded_files:
                        file_data = json.load(uploaded_file)
                        # Extract filename without .json extension
                        filename = uploaded_file.name.replace('.json', '')

                        # If file contains a dict, prepend filename to each key
                        if isinstance(file_data, dict):
                            for key, value in file_data.items():
                                # Create composite key: filename_originalkey
                                composite_key = f'{filename}_{key}'
                                all_data[composite_key] = value
                                total_entries += 1
                        else:
                            # Use filename (without .json) as key for list data
                            all_data[filename] = file_data
                            total_entries += len(file_data) if isinstance(file_data, list) else 1

                    st.success(f'✅ Loaded {len(uploaded_files)} file(s) with {total_entries} total entries')

                    with st.expander('📋 Preview uploaded data'):
                        first_key = list(all_data.keys())[0]
                        preview = (
                            all_data[first_key]
                            if isinstance(all_data[first_key], dict)
                            else {first_key: all_data[first_key]}
                        )
                        st.json(preview)
                        st.caption(f'Showing first entry from {total_entries} total entries')

                    data = all_data
                    needs_conversion = False
                    st.session_state['data_source'] = 'Uploaded'
                    st.session_state['use_folder_path'] = False
                    st.session_state['is_dual_response'] = False
                except Exception as e:
                    st.error(f'❌ Error loading files: {e}')

        else:  # Folder Path
            folder_path = st.text_input(
                '📁 Folder Path',
                placeholder='/path/to/json/files/',
                help='Path to folder containing JSON evaluation files',
                key='folder_path_input',
            )

            if folder_path and folder_path.strip():
                folder = Path(folder_path.strip())

                if folder.exists() and folder.is_dir():
                    # Count JSON files
                    json_files = list(folder.glob('*.json'))

                    if json_files:
                        st.success(f'✅ Found {len(json_files)} JSON file(s) in folder')

                        with st.expander('📋 Files in folder'):
                            for f in json_files[:10]:  # Show first 10
                                st.caption(f'• {f.name}')
                            if len(json_files) > 10:
                                st.caption(f'... and {len(json_files) - 10} more')

                        # Store folder path to pass to runner
                        data = str(folder)  # Pass folder path as string
                        needs_conversion = False
                        st.session_state['data_source'] = 'Uploaded'
                        st.session_state['use_folder_path'] = True
                        st.session_state['is_dual_response'] = False
                    else:
                        st.warning('⚠️ No JSON files found in folder')
                elif folder_path:
                    st.error(f'❌ Folder not found: {folder_path}')

    # Tab 3: Ad-hoc Input
    with tab_adhoc:
        st.info('💡 Create evaluation data by entering text directly')

        # Input fields
        col1, col2 = st.columns(2)

        with col1:
            source = st.text_area(
                '📄 Source Text',
                height=150,
                placeholder='Enter the source/reference text...',
                key='adhoc_source',
                help='Required: The original text or context',
            )

            response = st.text_area(
                '📝 Response Text',
                height=150,
                placeholder='Enter the response/output to evaluate...',
                key='adhoc_response',
                help='Required: The text to be evaluated',
            )

        with col2:
            question = st.text_area(
                '❓ Question (Optional)',
                height=100,
                placeholder='Enter the question if applicable...',
                key='adhoc_question',
                help='Optional: For Q&A evaluation mode',
            )

            response2 = st.text_area(
                '📝 Response 2 (Optional)',
                height=100,
                placeholder='Enter second response for comparison...',
                key='adhoc_response2',
                help='Optional: For comparison evaluation mode',
            )

            additional_data = st.text_area(
                '📋 Additional Data (Optional)',
                height=100,
                placeholder='Enter additional metadata as JSON...',
                key='adhoc_additional',
                help='Optional: Additional data in JSON format',
            )

        # Create eval JSON button and Clear button side by side
        btn_col1, btn_col2 = st.columns([3, 1])

        with btn_col1:
            if st.button('✨ Create Evaluation Data', type='primary', width='stretch', key='create_adhoc_btn'):
                if not source or not response:
                    st.error('❌ Source and Response are required')
                else:
                    try:
                        adhoc_data = _create_adhoc_eval_data(source, response, question, response2, additional_data)
                        st.session_state['adhoc_eval_data'] = adhoc_data
                        st.session_state['data_source'] = 'Ad-hoc'
                        st.success('✅ Evaluation data created')

                        with st.expander('📋 Preview created data'):
                            st.json(adhoc_data)

                        st.rerun()
                    except Exception as e:
                        st.error(f'❌ Error creating data: {e}')

        with btn_col2:
            if st.button(
                '🗑️ Clear All',
                type='secondary',
                width='stretch',
                key='clear_adhoc_btn',
                help='Clear all ad-hoc input fields',
            ):
                # Clear all ad-hoc related session state
                keys_to_clear = [
                    'adhoc_source',
                    'adhoc_response',
                    'adhoc_question',
                    'adhoc_response2',
                    'adhoc_additional',
                    'adhoc_eval_data',
                ]
                for key in keys_to_clear:
                    if key in st.session_state:
                        del st.session_state[key]

                # Clear data_source if it was Ad-hoc
                if st.session_state.get('data_source') == 'Ad-hoc':
                    del st.session_state['data_source']

                st.success('✅ All ad-hoc data cleared!')
                st.rerun()

        # Show created data if it exists
        if 'adhoc_eval_data' in st.session_state:
            st.success('✅ Ad-hoc evaluation data ready')
            with st.expander('📋 Preview ad-hoc data'):
                st.json(st.session_state['adhoc_eval_data'])

            data = st.session_state['adhoc_eval_data']
            needs_conversion = False
            st.session_state['data_source'] = 'Ad-hoc'
            st.session_state['is_dual_response'] = False
            st.session_state['use_folder_path'] = False

    # Return data from whichever tab was used
    if data is None:
        st.warning('⚠️ Please provide input data using one of the tabs above')
        return None, False

    return data, needs_conversion


def _get_evaluation_config(needs_conversion):
    """Get evaluation configuration"""
    st.subheader('⚙️ Configuration')

    # Main configuration in 3 columns
    col1, col2, col3 = st.columns([1, 2, 2])

    with col1:
        eval_mode = st.selectbox(
            '📊 Evaluation Mode',
            options=[mode.value for mode in EvaluationMode],
            help='Type of evaluation to perform',
        )

    with col2:
        model_options = [
            'gpt_4o_mini',
            'gpt_5_mini',
            'grok_mini',
            'grok_free',
            'xai/grok-3-mini',
            'groq_fast',
            'groq_llama_70b',
            'groq/llama-3.3-70b-versatile',
            'gemini-2.5-flash',
            'gemini-2.5-pro',
            'gpt_o3_mini',
            'gpt_5',
            'gpt_5_nano',
            'gpt_5_chat',
            'gpt_4o',
        ]
        _raw_defaults = os.environ.get('LLMJURY_DEFAULT_MODELS', 'gpt_4o_mini,gpt_5_mini')
        _parsed_defaults = [x.strip() for x in _raw_defaults.split(',') if x.strip()]
        model_defaults = [x for x in _parsed_defaults if x in model_options] or ['gpt_4o_mini', 'gpt_5_mini']
        models = st.multiselect(
            '🤖 Models',
            model_options,
            default=model_defaults,
            help='Select one or more models (set LLMJURY_DEFAULT_MODELS in .env for defaults). '
            'xAI Grok: XAI_API_KEY + models like grok_mini. Groq (e.g. Llama 3.3 70B): GROQ_API_KEY + groq_llama_70b '
            'or groq/llama-3.3-70b-versatile.',
        )

    with col3:
        # Criteria (for metrics mode)
        criteria = None
        if eval_mode == 'metrics':
            criteria = st.multiselect(
                '📏 Criteria',
                [c.value for c in EvaluationCriteria],
                default=['accuracy', 'comprehensiveness'],
                help='Select evaluation criteria',
            )

    # Result name and output path side by side
    col_a, col_b = st.columns(2)

    with col_a:
        result_name = st.text_input('🏷️ Result Name', value='evaluation', help='Output file suffix')

    with col_b:
        default_output = str(Path(__file__).parent.parent / 'temp_evaluations')
        output_path = st.text_input(
            '📁 Output Location', value=default_output, help='Directory where results will be saved'
        )

    calc_avg_std = st.checkbox('Calculate Stats', value=False, help='Calculate average and standard deviation')

    # Custom prompt
    use_custom = st.checkbox('Use custom prompt', key='use_custom_prompt')

    custom_prompt = None
    if use_custom:
        st.caption(
            '**Available variables:** `{source}`, `{response}`, `{question}`, `{criteria_name}`, `{additional_data}`'
        )
        custom_prompt = st.text_area(
            'Prompt Template',
            height=150,
            placeholder=(
                'Evaluate based on {criteria_name}:\n\n'
                'Source: {source}\n'
                'Response: {response}\n\n'
                'Score (1-5) and reasoning:'
            ),
            label_visibility='collapsed',
        )

    # Dashboard data options (only when using dashboard data)
    if needs_conversion:
        st.markdown('**🔄 Dashboard Data Options**')
        col_c, col_d = st.columns(2)
        with col_c:
            include_scores = st.checkbox(
                'Include existing scores',
                value=True,
                help='Include previous evaluation scores in additional_data',
            )
        with col_d:
            include_metadata = st.checkbox(
                'Include metadata', value=True, help='Include word counts, compression ratios, etc.'
            )
    else:
        include_scores = False
        include_metadata = False

    return {
        'eval_mode': eval_mode,
        'models': models,
        'criteria': criteria,
        'calc_avg_std': calc_avg_std,
        'result_name': result_name,
        'custom_prompt': custom_prompt,
        'include_scores': include_scores,
        'include_metadata': include_metadata,
        'output_path': output_path,
    }


def _run_evaluation_section(data, config, needs_conversion):
    """Run evaluation (same for all scenarios)."""
    st.subheader('🚀 Execute')

    # Check if auto-run is ready (from dashboard/comparison button click)
    auto_run_ready = st.session_state.get('auto_run_ready', False)

    if auto_run_ready:
        st.success('✅ **Ready for re-analysis!** Configuration is pre-filled with defaults.')

        # Clear the flag so it doesn't persist
        st.session_state['auto_run_ready'] = False

    # Validation
    if not config['models']:
        st.error('❌ Select at least one model')
        return

    if config['eval_mode'] == 'metrics' and not config['criteria'] and not config['custom_prompt']:
        st.error('❌ Select criteria or provide custom prompt')
        return

    # Create output directory
    output_dir = Path(config['output_path'])
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        st.error(f'❌ Cannot create output directory: {e}')
        return

    # Show preview of what will be executed
    use_folder_path = st.session_state.get('use_folder_path', False)
    data_source = st.session_state.get('data_source', 'Unknown')

    # Determine input path for preview
    if needs_conversion:
        input_path = Path(st.session_state.get('converted_data_path', 'Not converted yet'))
    elif use_folder_path:
        input_path = Path(data)
    else:
        input_path = output_dir / f'input_{config["result_name"]}.json'

    # Show command preview (only)
    with st.expander('🔍 Preview command & configuration', expanded=False):
        # Build CLI-style command
        input_label = 'Folder' if use_folder_path else 'File'
        cli_command = f"""python runners/run_llmjury_evaluator.py \\
  --eval_json_path {input_path} \\
  --name {config["result_name"]} \\
  --models {' '.join(config['models'])}"""

        if config['criteria']:
            cli_command += f""" \\
  --criteria {' '.join(config['criteria'])}"""

        if config['calc_avg_std']:
            cli_command += """ \\
  --calc_avg_and_std"""

        if config['custom_prompt']:
            prompt_preview = config['custom_prompt'][:50].replace('\n', ' ') + '...'
            cli_command += f""" \\
  --custom_prompt_template "{prompt_preview}" """

        cli_command += f""" \\
  --evaluation_mode {config["eval_mode"]} \\
  --output_dir {output_dir}"""

        st.markdown('**CLI Command:**')
        st.code(cli_command, language='bash')

        st.markdown('**Configuration:**')
        config_summary = f"""
- **Data Source:** `{data_source}`
- **Evaluation Mode:** `{config['eval_mode']}`
- **Models:** `{', '.join(config['models'])}`
- **Criteria:** `{', '.join(config['criteria']) if config['criteria'] else 'Custom prompt template'}`
- **Result Name:** `{config['result_name']}`
- **Calculate Stats:** `{'Yes' if config['calc_avg_std'] else 'No'}`
- **Input {input_label}:** `{input_path}`
- **Output Directory:** `{output_dir}`
"""
        if config['custom_prompt']:
            config_summary += f"""- **Custom Prompt Length:** `{len(config['custom_prompt'])} characters`"""

        st.markdown(config_summary)
        st.caption('💡 Copy the CLI command to run evaluation from terminal')

    # Run button
    # Check if we just came from dashboard/comparison
    is_from_dashboard = st.session_state.get('data_source') in ['Dashboard', 'Dual-Response']

    # Use full width for more prominent button when coming from dashboard
    if is_from_dashboard:
        button_cols = st.columns([1, 3, 1])
    else:
        button_cols = st.columns([1, 2, 1])

    with button_cols[1]:
        # Can run if: (1) not dashboard data, or (2) dashboard data has been converted
        can_run = not needs_conversion or 'converted_data_path' in st.session_state
        run_button = st.button('▶️ Run Evaluation', type='primary', width='stretch', disabled=not can_run)

        if not can_run:
            st.caption('⚠️ Convert dashboard data first (see Input Data section above)')

    # Display results below execution section if they exist (persists across button clicks)
    if not run_button:
        # Show results even when button not clicked (for persistence)
        if 'last_eval_results' in st.session_state and not st.session_state.get('evaluation_running', False):
            st.markdown('---')
            _display_evaluation_results()
        return

    # Determine input file or folder
    use_folder_path = st.session_state.get('use_folder_path', False)
    is_dual_response = st.session_state.get('is_dual_response', False)

    # Validate data type consistency with flags
    if is_dual_response and not isinstance(data, list):
        st.error('❌ Error: Dual-response mode expects list data, but got different type. Please reload your data.')
        return
    if use_folder_path and not isinstance(data, str):
        st.error('❌ Error: Folder path mode expects string data, but got different type. Please reload your data.')
        return

    if needs_conversion:
        # Use converted dashboard data (single-response)
        input_path = Path(st.session_state['converted_data_path'])
    elif is_dual_response:
        # Save dual-response data to output dir
        # Format: {key: {source, response1, response2, label1, label2, ...}}
        input_path = output_dir / f'dual_response_{config["result_name"]}.json'

        # Convert list to dict format expected by LLMJury
        dual_dict = {}
        for item in data:
            # Ensure item is a dict, not a string
            if not isinstance(item, dict):
                st.error(f'❌ Error: Expected dict in dual-response data, got {type(item).__name__}. Item: {item}')
                return

            # Create key from filename and section_id
            filename = item.get('filename', 'unknown')
            section_id = item.get('section_id', '')
            key = f'{filename}_{section_id}' if section_id else filename

            # Store with all fields
            dual_dict[key] = {
                'source': item['source'],
                'response': item['response1'],  # Primary response
                'response2': item['response2'],  # Secondary response for comparison
                'label1': item.get('label1', 'a'),
                'label2': item.get('label2', 'b'),
            }

            # Add optional fields
            if 'question' in item:
                dual_dict[key]['question'] = item['question']

        with open(input_path, 'w', encoding='utf-8') as f:
            json.dump(dual_dict, f, indent=2, ensure_ascii=False)

        st.info(f'💡 Dual-response data saved to: `{input_path.name}`')
    elif use_folder_path:
        # Use folder path directly (data is already the folder path string)
        input_path = Path(data)
    else:
        # Save uploaded JSON/ad-hoc data to output dir
        input_path = output_dir / f'input_{config["result_name"]}.json'
        with open(input_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # Run evaluation
    st.session_state['evaluation_running'] = True
    _execute_evaluation(input_path, config, output_dir, use_folder_path)
    st.session_state['evaluation_running'] = False

    # Rerun to display results below
    st.rerun()


def _convert_and_save_data(data, config, output_dir):
    """Convert dashboard data and save to output directory."""
    try:
        with st.spinner('🔄 Converting data...'):
            # Convert
            converted = convert_dashboard_export_to_eval_format(
                data, config['include_scores'], config['include_metadata']
            )

            # Save converted data
            converted_file = output_dir / 'converted_for_evaluation.json'
            with open(converted_file, 'w', encoding='utf-8') as f:
                json.dump(converted, f, indent=2, ensure_ascii=False)

            # Save custom prompt if provided
            prompt_file = None
            if config['custom_prompt']:
                prompt_file = output_dir / 'custom_prompt.txt'
                with open(prompt_file, 'w', encoding='utf-8') as f:
                    f.write(config['custom_prompt'])

            # Store paths and count in session state
            st.session_state['converted_data_path'] = str(converted_file)
            st.session_state['custom_prompt_path'] = str(prompt_file) if prompt_file else None
            st.session_state['converted_count'] = len(converted)

    except Exception as e:
        st.error(f'❌ Conversion failed: {e}')
        import traceback

        st.code(traceback.format_exc())


def _execute_evaluation(input_path, config, output_dir, use_folder_path=False):
    """Execute the LLMJury evaluation with live logging."""
    _cleanup_old_files(output_dir)

    with st.status('🚀 Running Evaluation...', expanded=True) as status:
        try:
            # Just show a simple progress message
            st.write('⏳ Starting evaluation...')

            # Prepare evaluation script (repo root must be on path for `runners` + `llmjury`)
            repo_root = Path(__file__).resolve().parent.parent

            eval_script = f"""
import sys
import os
from pathlib import Path

_repo = Path(r'{repo_root}')
sys.path.insert(0, str(_repo))

from llmjury.env_bootstrap import load_llmjury_env
load_llmjury_env(repo_root=_repo)

# Change to output directory so results are saved there
os.chdir(r'{output_dir}')

from runners.run_llmjury_evaluator import llm_evaluator
from llmjury.constants import EvaluationMode

llm_evaluator(
    eval_json_path=Path('{input_path}'),
    criteria_to_be_evaluated={config['criteria'] if config['criteria'] else None},
    models={config['models']},
    name='{config["result_name"]}',
    calc_avg_and_std={config['calc_avg_std']},
    custom_prompt_template={repr(config['custom_prompt']) if config['custom_prompt'] else None},
    evaluation_mode=EvaluationMode('{config['eval_mode']}'),
)

print(f'\\n✅ Results saved to: {output_dir}')
"""

            # Write and execute script
            script_file = output_dir / 'run_eval.py'
            with open(script_file, 'w') as f:
                f.write(eval_script)

            # Run as subprocess
            process = subprocess.Popen(
                [sys.executable, str(script_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Capture output in collapsible logs
            output_lines = []

            # Create expander for logs (collapsible)
            with st.expander('📋 Live Logs', expanded=True):
                log_placeholder = st.empty()

                for line in process.stdout:
                    output_lines.append(line.rstrip())
                    log_text = '\n'.join(output_lines[-100:])  # Last 100 lines
                    log_placeholder.code(log_text, language='log')

            return_code = process.wait()

            # Close the status widget - we'll show results outside it
            if return_code == 0:
                status.update(label='✅ Evaluation Completed!', state='complete', expanded=False)
            else:
                status.update(label='❌ Evaluation Failed', state='error', expanded=False)

        except Exception as e:
            status.update(label='❌ Error', state='error', expanded=False)
            st.error(f'Error: {e}')
            import traceback

            st.code(traceback.format_exc())
            return

    # Show results OUTSIDE the status widget (not collapsible)
    result_excel = output_dir / f'llm_evaluation_results_{config["result_name"]}.xlsx'
    result_json = output_dir / f'llm_evaluation_results_{config["result_name"]}.json'

    # Store results in session state (even for failed runs to preserve logs)
    st.session_state['last_eval_results'] = {
        'excel_path': str(result_excel),
        'json_path': str(result_json),
        'output_dir': str(output_dir),
        'logs': output_lines,
        'success': return_code == 0,
    }

    if return_code == 0:
        st.balloons()
    else:
        st.error(f'❌ Evaluation failed with exit code {return_code}')
        with st.expander('📋 Full Log', expanded=True):
            st.code('\n'.join(output_lines), language='log')


def _display_evaluation_results():
    """Display evaluation results section (persists across reruns)."""
    if 'last_eval_results' not in st.session_state:
        return

    results = st.session_state['last_eval_results']
    result_excel = Path(results['excel_path'])
    result_json = Path(results['json_path'])
    output_dir = Path(results['output_dir'])
    is_success = results.get('success', True)

    # For failed evaluations, show error and logs only
    if not is_success:
        st.error('❌ **Evaluation failed** - Logs available below')
        logs_text = '\n'.join(results.get('logs', []))
        if logs_text:
            col1, col2 = st.columns([3, 1])
            with col1:
                with st.expander('📋 View Logs', expanded=False):
                    st.code(logs_text, language='log')
            with col2:
                st.download_button(
                    '⬇️ Download Logs',
                    logs_text,
                    'evaluation_error_logs.txt',
                    'text/plain',
                    key='download_failed_logs',
                )
        if st.button('🗑️ Clear', key='clear_failed_results'):
            del st.session_state['last_eval_results']
            st.rerun()
        return

    # Check if files still exist (for successful runs)
    if not result_excel.exists() and not result_json.exists():
        st.warning('⚠️ Previous evaluation results no longer available')
        if st.button('🗑️ Clear', key='clear_old_results'):
            del st.session_state['last_eval_results']
            st.rerun()
        return

    # Success section (always visible, not collapsible)
    st.success('✅ **Evaluation completed successfully!**')

    # Results section with download and load buttons
    st.markdown('### 📁 Results')

    # Read files for download
    excel_data = None
    json_data = None

    if result_excel.exists():
        with open(result_excel, 'rb') as f:
            excel_data = f.read()

    if result_json.exists():
        with open(result_json, encoding='utf-8') as f:
            json_data = f.read()

    # Show file paths in compact format
    st.markdown(f'**📊 Excel:** `{result_excel.name}`')
    st.markdown(f'**📋 JSON:** `{result_json.name}`')
    st.markdown(f'**📁 Location:** `{output_dir}`')

    # Prepare logs for download
    logs_text = '\n'.join(results['logs'])
    log_filename = f'evaluation_logs_{result_excel.stem}.txt'

    # Action buttons - Row 1: File downloads
    col1, col2, col3 = st.columns(3)

    with col1:
        if excel_data:
            st.download_button(
                '⬇️ Download Excel',
                excel_data,
                result_excel.name,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='download_excel_result',
                width='stretch',
                help='Download Excel results file',
            )

    with col2:
        if json_data:
            st.download_button(
                '⬇️ Download JSON',
                json_data,
                result_json.name,
                'application/json',
                key='download_json_result',
                width='stretch',
                help='Download LLMJury JSON results',
            )

    with col3:
        if logs_text:
            st.download_button(
                '⬇️ Download Logs',
                logs_text,
                log_filename,
                'text/plain',
                key='download_logs_result',
                width='stretch',
                help='Download execution logs as text file',
            )

    # Action buttons - Row 2: Actions
    col4, col5, col6 = st.columns(3)

    with col4:
        if excel_data and st.button(
            '📊 Load in Dashboard',
            key='load_results_dashboard',
            width='stretch',
            help='Load results directly in Dashboard tab',
        ):
            try:
                data = load_excel_all_sheets(str(result_excel))
                st.session_state['dashboard_data'] = data
                st.session_state['dashboard_filename'] = result_excel.name
                st.success('✅ Loaded in Dashboard!')
                st.info('👉 Switch to **Dashboard** tab to view results')
            except Exception as e:
                st.error(f'❌ Failed to load: {e}')

    with col5:
        if st.button('📂 Copy Path', key='copy_output_path', width='stretch', help='Show full output path'):
            st.code(str(output_dir), language='bash')

    with col6:
        # View logs inline toggle
        if st.button('👁️ View Logs', key='toggle_logs_view', width='stretch', help='Toggle logs display'):
            st.session_state['show_logs_inline'] = not st.session_state.get('show_logs_inline', False)

    # Show logs inline if toggled
    if st.session_state.get('show_logs_inline', False):
        with st.expander('📋 Execution Logs', expanded=True):
            st.code(logs_text, language='log')

    # Clear results button (small, at bottom)
    if st.button('🗑️ Clear Results', key='clear_results_btn', help='Clear this results section'):
        del st.session_state['last_eval_results']
        st.rerun()
