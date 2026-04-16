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
Field name mappings for LLM Jury evaluation.

This module defines the recognized field names for different data types
in evaluation datasets. These mappings enable flexible data format support
and automatic field detection.
"""

# Field name mappings for extensibility and dynamic detection
# These lists can be easily extended to support new field names without changing core logic
PROMPT_FIELD_NAMES = ['source', 'prompt', 'section_text', 'ground_truth', 'context', 'source_text', 'reference_text']
ANSWER_FIELD_NAMES = ['response', 'summary', 'answer', 'output', 'result', 'prediction']
QUESTION_FIELD_NAMES = ['question', 'query', 'prompt_text', 'instruction']

COMPARISON_FIELD_NAMES_1 = [
    'summary1',
    'response1',
    'answer1',
    'option_a',
    'text1',
    'candidate1',
    'output1',
]
COMPARISON_FIELD_NAMES_2 = [
    'summary2',
    'response2',
    'answer2',
    'option_b',
    'text2',
    'candidate2',
    'output2',
]

# Alternative field names for reasoning in JSON responses
REASONING_FIELD_NAMES = ['reasoning', 'explanation', 'analysis', 'justification']

# Metadata field names for content classification
CONTENT_TYPE_FIELD_NAMES = ['content_type', 'summary_type', 'type']

# Additional information field names for supplementary context
ADDITIONAL_INFO_FIELD_NAMES = ['additional_info', 'additional_details', 'extra_info', 'metadata', 'notes', 'details']
