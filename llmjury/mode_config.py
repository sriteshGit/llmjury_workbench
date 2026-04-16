# LLMJury Workbench

"""
Mode configuration for LLM Jury evaluation modes.

NORMALIZED COLUMNS:
    - source_word_count:     Reference text
    - response_word_count:   Output text
    - response_a_word_count: First comparison output
    - response_b_word_count: Second comparison output
"""

from dataclasses import dataclass

from llmjury.constants import EvaluationMode


@dataclass
class ModeConfig:
    """
    Mode-specific configuration.

    Attributes
    ----------
    mode: Evaluation mode
    word_count_fields: Fields to generate word counts for (auto-adds '_word_count' suffix)
    needs_compression: Calculate compression ratio for source vs response
    """

    mode: EvaluationMode
    word_count_fields: list[str]
    needs_compression: bool

    @property
    def index_columns(self) -> list[str]:
        """Word count columns + compression (if enabled)."""
        cols = [f'{field}_word_count' for field in self.word_count_fields]
        if self.needs_compression:
            cols.append('compression_ratio_percentage')
        return cols


MODE_CONFIGS = {
    EvaluationMode.METRICS: ModeConfig(
        mode=EvaluationMode.METRICS,
        word_count_fields=['source', 'response'],
        needs_compression=True,
    ),
    EvaluationMode.QUESTION_ANSWER: ModeConfig(
        mode=EvaluationMode.QUESTION_ANSWER,
        word_count_fields=['source', 'response'],
        needs_compression=False,
    ),
    EvaluationMode.COMPARISON: ModeConfig(
        mode=EvaluationMode.COMPARISON,
        word_count_fields=['source', 'response_a', 'response_b'],
        needs_compression=False,
    ),
}


def get_mode_config(mode: EvaluationMode) -> ModeConfig:
    """Get configuration for evaluation mode."""
    if mode not in MODE_CONFIGS:
        raise ValueError(f'Unsupported mode: {mode}. Available: {list(MODE_CONFIGS.keys())}')
    return MODE_CONFIGS[mode]
