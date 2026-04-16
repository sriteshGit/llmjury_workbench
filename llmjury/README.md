# LLM Multi-Mode Evaluation

## Overview
LLM Multi-Mode Evaluation is a comprehensive evaluation framework for assessing various content types (summaries, Q&A responses, comparisons) using multiple LLM models. It provides multi-dimensional analysis across different evaluation modes (metrics, question_answer, comparison) and supports various content types including summaries, overviews, podcasts, and DAA agent responses.

## Key Features
- Multi-model evaluation using different LLM providers (GPT-4, Gemini, Claude)
- Comprehensive evaluation criteria
- Detailed reasoning for each evaluation
- Token count and compression ratio metrics
- Excel-based reporting with visual formatting

## Evaluation Criteria

### 1. Accuracy
Evaluates how accurately the summary represents the key information from the source text.

### 2. Truthfulness
Assesses whether the summary contains any factual inaccuracies or hallucinations.

### 3. Comprehensiveness
Measures how well the summary covers the important points from the source text.

### 4. Conciseness
Evaluates the efficiency of information delivery, focusing on:
- Information density
- Redundancy
- Word economy
- Focus on essential information

### 5. Duplicacy
Assesses the presence of repeated or redundant content within the summary itself:
- Self-repetition
- Redundant phrases
- Circular reasoning

### 6. Additional Criteria
- Balance
- Clarity
- Coherence
- Navigation

## Scoring System
Each criterion is scored on a scale of 1-5:
- 5: Excellent
- 4: Good
- 3: Satisfactory
- 2: Needs Improvement
- 1: Poor

## Technical Implementation

### Required Dependencies
- openpyxl
- pandas
- langchain-core
- litellm (routes to OpenAI, Anthropic, Azure, Gemini, etc. via provider env vars)

### Model Support
The framework supports multiple LLM models:
- GPT-4 (various versions)
- Gemini (various versions)
- Claude (various versions)

### Output Format
The evaluation generates:
1. JSON file with detailed results
2. Excel file with:
   - Main sheet: Detailed evaluation results
   - Report sheet: Summary statistics
   - Visual formatting for scores (red for ≤3, green for >3)

## Usage

### Command Line Interface
```bash
python runners/run_llmjury_evaluator.py --eval_json_path /path/to/json --criteria comprehensiveness conciseness --models gpt_4o_mini gpt-4o --name test_run
```

### Arguments
- `--eval_json_path`: Path to evaluation JSON files (required)
- `--criteria`: List of criteria to evaluate (default: ['accuracy', 'truthfulness'])
- `--models`: List of models to use (default: ['GPT_4O_0513'])
- `--name`: Suffix for output files (optional)

### Available Criteria
- accuracy
- balance
- clarity
- coherence
- comprehensiveness
- conciseness
- navigation
- truthfulness
- duplicacy

### Available Models
- GPT_4O_MINI
- GPT_4O_0513
- GEMINI_20_FLASH
- GEMINI_20_PRO
- BEDROCK_CLAUDE_3_SONNET
- BEDROCK_CLAUDE_3_OPUS

## Metrics

### Token Count
- Section token count: Number of tokens in the source text
- Summary token count: Number of tokens in the summary
- Compression ratio: Ratio of section tokens to summary tokens

### Evaluation Metrics
- Total non-blank sections
- Sections with score >3
- Percentage of sections with score >3

## Best Practices

### Running Evaluations
1. Ensure all required dependencies are installed
2. Prepare input JSON files with proper formatting
3. Select appropriate criteria based on evaluation goals
4. Choose models based on availability and requirements
5. Review output files for comprehensive analysis

### Interpreting Results
1. Consider both individual scores and aggregate statistics
2. Pay attention to reasoning for low scores
3. Use token metrics to assess efficiency
4. Compare results across different models
5. Look for patterns in specific criteria

## Troubleshooting

### Common Issues
1. Missing dependencies
2. Invalid JSON format
3. Model availability issues
4. Token counting errors
5. Excel file generation problems

### Solutions
1. Install all required packages
2. Validate JSON structure
3. Check model availability and credentials
4. Verify tokenizer configuration
5. Ensure proper Excel file permissions

## Future Enhancements
- Support for additional LLM models
- New evaluation criteria
- Enhanced visualization options
- Automated report generation
- Integration with additional metrics
