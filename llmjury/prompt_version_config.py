# LLMJury Workbench


"""
Configuration for mapping content types and evaluation modes to prompt versions.

This module provides a hierarchical configuration system that maps different content types
(e.g., 'summary', 'overview', 'podcast') and evaluation modes (e.g., 'metrics', 'comparison', 'question_answer')
to specific prompt versions for each evaluation criteria. This allows for targeted prompt selection
based on both the content type and evaluation context.

If a content type is not found, the system falls back to the 'summary' content type.
"""

import json
import logging
import os
import threading
from typing import Any

from llmjury.constants import (
    DEFAULT_COMPARISON_VERSION,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_EVALUATION_MODE,
    DEFAULT_METRICS_VERSION,
    DEFAULT_QUESTION_ANSWER_VERSION,
    PROMPT_CONFIG_BASE_VERSION_KEY,
    PROMPT_CONFIG_CUSTOMIZATION_KEYS_KEY,
    PROMPT_VERSIONS_CONFIG_FILE,
)

logger = logging.getLogger(__name__)


class PromptVersionConfig:
    """
    Configuration class for mapping content types and evaluation modes to prompt versions.

    This class provides a centralized, read-only configuration loaded from a JSON file at startup.
    All operations are thread-safe via internal locking.

    Public API:
        - load_config(path): Load configuration from JSON file
        - get_prompt_version(criteria, content_type, mode, customization_data): Get versioned prompt for criteria
        - get_mode_prompt_version(mode_key, content_type, mode): Get versioned prompt for Q&A/comparison

    Fallback behavior: Unknown content types fall back to 'summary'.
    """

    PROMPT_MAPPINGS: dict[str, Any] = {}
    _config_lock = threading.Lock()
    DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), PROMPT_VERSIONS_CONFIG_FILE)

    @staticmethod
    def _normalize_inputs(content_type: str | None, evaluation_mode: str | None) -> tuple[str, str]:
        """Normalize content_type and evaluation_mode to lowercase.

        This is the single point of normalization for all public methods.

        Parameters
        ----------
        content_type : str | None
            The content type to normalize
        evaluation_mode : str | None
            The evaluation mode to normalize

        Returns
        -------
        tuple[str, str]
            Normalized (content_type, evaluation_mode) both in lowercase
        """
        normalized_content_type = (content_type or DEFAULT_CONTENT_TYPE).lower()
        normalized_evaluation_mode = (evaluation_mode or DEFAULT_EVALUATION_MODE).lower()
        return normalized_content_type, normalized_evaluation_mode

    @classmethod
    def get_mode_prompt_version(
        cls, mode_key: str, content_type: str | None = None, evaluation_mode: str | None = None
    ) -> str:
        """Get prompt version for Q&A and Comparison modes.

        This is a simplified version lookup for mode-specific prompts without
        the complex customization logic needed for metrics criteria.

        Parameters
        ----------
        mode_key : str
            The mode key (e.g., 'question_answer', 'comparison_with_source')
        content_type : str, optional
            The content type (e.g., 'summary', 'overview')
        evaluation_mode : str, optional
            The evaluation mode (e.g., 'question_answer', 'comparison')

        Returns
        -------
        str
            The version string for the mode
        """
        # Normalize inputs (single point of normalization)
        content_type, evaluation_mode = cls._normalize_inputs(content_type, evaluation_mode)

        try:
            # Try to get from content type specific config
            if content_type and evaluation_mode:
                config = cls._get_content_config(content_type, evaluation_mode)
                if mode_key in config:
                    version = config[mode_key]
                    if isinstance(version, str) and version:
                        return version
        except Exception as e:
            logger.debug(f'Error getting mode version for {mode_key}: {e}')

        # Intelligent fallback based on mode_key
        if 'comparison' in mode_key:
            return DEFAULT_COMPARISON_VERSION
        if mode_key == 'question_answer' or 'qna' in mode_key:
            return DEFAULT_QUESTION_ANSWER_VERSION
        return DEFAULT_METRICS_VERSION

    @classmethod
    def load_config(cls, config_path: str | None = None) -> None:
        """Load configuration from a JSON file.

        If config_path is None, it loads from the default path.
        """
        path_to_load = config_path or cls.DEFAULT_CONFIG_PATH  # Keep this as class attribute
        try:
            with open(path_to_load) as f:
                config_data = json.load(f)
            with cls._config_lock:
                cls.PROMPT_MAPPINGS = config_data
            logger.info(f'Loaded prompt configuration from {path_to_load}')

        except (FileNotFoundError, json.JSONDecodeError) as e:
            # Fallback to an empty config if default is not found or corrupt
            logger.warning(
                'Could not load prompt config from %s. Error: %s. Falling back to empty config.', path_to_load, e
            )
            with cls._config_lock:
                cls.PROMPT_MAPPINGS = {}

    @classmethod
    def _get_content_config(cls, content_type: str | None, evaluation_mode: str | None = None) -> dict[str, Any]:
        """Get the configuration for a specific content type and evaluation mode with fallback to summary.

        Note: Expects content_type and evaluation_mode to already be normalized to lowercase by caller.
        """
        requested_content_type = content_type or DEFAULT_CONTENT_TYPE
        requested_evaluation_mode = evaluation_mode or DEFAULT_EVALUATION_MODE

        with cls._config_lock:
            # Try exact match first
            if requested_content_type in cls.PROMPT_MAPPINGS:
                content_config = cls.PROMPT_MAPPINGS[requested_content_type]

                if requested_evaluation_mode in content_config:
                    mode_config = content_config[requested_evaluation_mode]
                    return mode_config if isinstance(mode_config, dict) else {}
                else:
                    logger.warning(
                        "Evaluation mode '%s' not found for content type '%s'. Using default mode '%s'.",
                        requested_evaluation_mode,
                        requested_content_type,
                        DEFAULT_EVALUATION_MODE,
                    )
                    default_config = content_config.get(DEFAULT_EVALUATION_MODE, {})
                    return default_config if isinstance(default_config, dict) else {}
            else:
                logger.warning(
                    "Content type '%s' not found. Falling back to default content type '%s'.",
                    requested_content_type,
                    DEFAULT_CONTENT_TYPE,
                )
                # Avoid infinite recursion by checking if default content type exists
                if DEFAULT_CONTENT_TYPE in cls.PROMPT_MAPPINGS:
                    fallback_config = cls.PROMPT_MAPPINGS.get(DEFAULT_CONTENT_TYPE, {})
                    if requested_evaluation_mode and requested_evaluation_mode in fallback_config:
                        mode_config = fallback_config[requested_evaluation_mode]
                        return mode_config if isinstance(mode_config, dict) else {}
                    elif DEFAULT_EVALUATION_MODE in fallback_config:
                        default_mode_config = fallback_config[DEFAULT_EVALUATION_MODE]
                        return default_mode_config if isinstance(default_mode_config, dict) else {}
                    else:
                        return {}
                else:
                    logger.error(f"Default content type '{DEFAULT_CONTENT_TYPE}' not found in configuration.")
                    return {}

    @classmethod
    def _extract_version_from_criteria_config(
        cls, criteria_config: str | dict[str, Any] | None, customization_data: dict[str, Any] | None
    ) -> str:
        """Extract version string from criteria configuration.

        Handles simple string versions, dict with base_version and customization keys,
        and returns default if config is None or invalid.

        Parameters
        ----------
        criteria_config : str | dict[str, Any] | None
            Configuration for the criteria (can be simple string version or dict with customization)
        customization_data : dict[str, Any] | None
            Data dictionary containing customization fields (e.g., summary_customization_length)
            Only the fields specified in _customization_keys_ will be used
        """
        if isinstance(criteria_config, str):
            return criteria_config

        if isinstance(criteria_config, dict):
            base_version_raw = criteria_config.get(PROMPT_CONFIG_BASE_VERSION_KEY, DEFAULT_METRICS_VERSION)
            base_version = str(base_version_raw)
            customization_keys = criteria_config.get(PROMPT_CONFIG_CUSTOMIZATION_KEYS_KEY, [])

            # If no keys or no data to check against, return base version
            if not customization_keys or not customization_data:
                return base_version

            # Build version with customization suffixes from specified keys only
            parts_to_add = [
                str(customization_data.get(key)) for key in customization_keys if customization_data.get(key)
            ]
            return f"{base_version}_{'_'.join(parts_to_add)}" if parts_to_add else base_version

        # Return default for None or any other type
        return DEFAULT_METRICS_VERSION

    @classmethod
    def get_prompt_version(
        cls,
        criteria: str,
        content_type: str | None = None,
        evaluation_mode: str | None = None,
        customization_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Get the full prompt version string for a specific criteria, content type, and evaluation mode.

        This is the main method for getting prompt versions with full context support.

        Parameters
        ----------
        criteria : str
            The criteria name (e.g., 'accuracy', 'comprehensiveness')
        content_type : str, optional
            The content type (e.g., 'summary', 'overview', 'podcast')
        evaluation_mode : str, optional
            The evaluation mode (e.g., 'metrics', 'comparison', 'question_answer')
        customization_data : dict[str, Any], optional
            Optional data for dynamic version customization (e.g., {'summary_customization_length': 'long'})
            Only used if criteria config has _customization_keys_ defined

        Returns
        -------
        str
            The full prompt version string (e.g., 'v2', 'v2_long')
        """
        # Normalize inputs (single point of normalization)
        content_type, evaluation_mode = cls._normalize_inputs(content_type, evaluation_mode)

        # Get configuration with fallback to summary
        config = cls._get_content_config(content_type, evaluation_mode)
        criteria_config = config.get(criteria)

        # If criteria not found in the requested content type, search other content types
        if not criteria_config and content_type == DEFAULT_CONTENT_TYPE:
            logger.warning(f"Criteria '{criteria}' not found in default content type '{content_type}'.")
            with cls._config_lock:
                content_types = list(cls.PROMPT_MAPPINGS.keys())
            for other_content_type in content_types:
                if other_content_type != content_type:
                    other_config = cls._get_content_config(other_content_type, evaluation_mode)
                    other_criteria_config = other_config.get(criteria)
                    if other_criteria_config:
                        logger.info(f"Found criteria '{criteria}' in content type '{other_content_type}'")
                        criteria_config = other_criteria_config
                        break

        # Extract version using common logic
        return cls._extract_version_from_criteria_config(criteria_config, customization_data)


# Load the default configuration when the module is imported
PromptVersionConfig.load_config()
