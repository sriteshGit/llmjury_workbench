# LLMJury Workbench

"""Convert dashboard exported data to LLMJury evaluation format."""

import json
from pathlib import Path
from typing import Any


def convert_dashboard_export_to_eval_format(
    exported_data: list[dict[str, Any]],
    include_existing_scores: bool = True,
    include_metadata: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Convert dashboard-exported JSON to LLMJury evaluation format.

    Args:
        exported_data: List of rows exported from dashboard
        include_existing_scores: Include existing evaluation scores in additional_data
        include_metadata: Include metadata like word counts, compression ratio

    Returns:
        Dictionary in LLMJury format: {section_id: {source, response, additional_data}}
    """
    converted = {}

    # Fields that are core evaluation inputs
    # core_fields = {'source', 'response', 'filename', 'section_id'}

    # Fields that are existing scores/reasoning
    score_fields = {
        k
        for k in (exported_data[0].keys() if exported_data else [])
        if any(suffix in k for suffix in ['_score', '_reasoning', '_definition'])
    }

    # Fields that are metadata
    metadata_fields = {
        k
        for k in (exported_data[0].keys() if exported_data else [])
        if any(meta in k for meta in ['word_count', 'compression', 'overall'])
    }

    for row in exported_data:
        # Create composite key: filename_sectionid
        filename = row.get('filename', 'unknown')
        section_id = row.get('section_id', f'row_{len(converted)}')
        composite_key = f'{filename}_{section_id}'

        # Core data - only source and response
        eval_entry = {
            'source': row.get('source', ''),
            'response': row.get('response', ''),
        }

        # Collect ALL other fields in additional_data as strings
        additional_data = {}

        for field, value in row.items():
            # Skip core fields that are already in eval_entry
            if field in {'source', 'response', 'section_id'}:
                continue

            # Add all other fields to additional_data
            if value is not None:
                # Convert all values to strings for consistency
                additional_data[field] = str(value)

        # Only add additional_data if we want to include it
        if additional_data and (include_existing_scores or include_metadata):
            # Filter based on preferences
            if not include_existing_scores:
                # Remove score fields
                additional_data = {k: v for k, v in additional_data.items() if k not in score_fields}

            if not include_metadata:
                # Remove metadata fields
                additional_data = {k: v for k, v in additional_data.items() if k not in metadata_fields}

            if additional_data:
                eval_entry['additional_data'] = additional_data

        converted[composite_key] = eval_entry

    return converted


def save_for_llmjury_evaluation(
    exported_json_path: Path,
    output_path: Path,
    include_existing_scores: bool = True,
    include_metadata: bool = True,
) -> Path:
    """
    Convert exported dashboard JSON to LLMJury evaluation format and save.

    Args:
        exported_json_path: Path to dashboard-exported JSON
        output_path: Path where converted JSON should be saved
        include_existing_scores: Include existing scores in additional_data
        include_metadata: Include metadata fields

    Returns:
        Path to the saved converted file
    """
    # Load exported data
    with open(exported_json_path, encoding='utf-8') as f:
        exported_data = json.load(f)

    # Convert to LLMJury format
    converted = convert_dashboard_export_to_eval_format(
        exported_data,
        include_existing_scores=include_existing_scores,
        include_metadata=include_metadata,
    )

    # Save converted data
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)

    return output_path


def prepare_evaluation_command(
    converted_json_path: Path,
    custom_prompt: str | None = None,
    prompt_file: Path | None = None,
    criteria: list[str] | None = None,
    models: list[str] | None = None,
    output_name: str = 'reanalysis',
    use_prompt_file: bool = False,
) -> str:
    """
    Generate command to run LLMJury evaluation with data and prompt separated.

    Args:
        converted_json_path: Path to evaluation data JSON file (contains source, response, additional_data)
        custom_prompt: Custom prompt template string (for inline passing)
        prompt_file: Path to separate prompt file (for file-based passing)
        criteria: Evaluation criteria list
        models: Model list
        output_name: Name suffix for output files
        use_prompt_file: If True, reads prompt from file; if False, passes inline

    Returns:
        Command string with data and prompt as separate arguments

    Note:
        - Eval JSON contains ONLY data (source, response, additional_data)
        - Custom prompt is passed separately via --custom_prompt_template
        - This ensures clean separation of data and evaluation instructions
    """
    cmd_parts = [
        'python',
        'runners/run_llmjury_evaluator.py',
        f'--eval_json_path {converted_json_path}',
        f'--name {output_name}',
    ]

    if custom_prompt:
        if use_prompt_file and prompt_file:
            # Read prompt from file approach (cleaner)
            cmd_parts.append(f'--custom_prompt_template "$(cat {prompt_file})"')
        else:
            # Inline prompt approach
            escaped_prompt = custom_prompt.replace('"', '\\"').replace('\n', '\\n')
            cmd_parts.append(f'--custom_prompt_template "{escaped_prompt}"')

    if criteria:
        cmd_parts.append(f'--criteria {" ".join(criteria)}')

    if models:
        cmd_parts.append(f'--models {" ".join(models)}')

    return ' \\\n    '.join(cmd_parts)
