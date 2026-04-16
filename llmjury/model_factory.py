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
"""Model factory for LLM Jury - supports factory models and Azure deployments."""

from venice_gentech.common.llm import llms
from venice_gentech.common.llm.llm_wrapper import AzureChatModel, ModelClass, ModelFactory


def get_available_factory_models() -> dict[str, ModelFactory]:
    """Discover all available factory models from llms module."""
    factory_models = {}
    for obj_name in dir(llms):
        obj = getattr(llms, obj_name)
        if isinstance(obj, ModelFactory) and hasattr(obj, 'model_class'):
            factory_models[obj_name.lower()] = obj
    return factory_models


# Cache available models
_MODEL_FACTORY_MODELS = get_available_factory_models()


def get_available_models() -> list[str]:
    """Get list of all available factory model names."""
    return list(_MODEL_FACTORY_MODELS.keys())


def is_azure_model(model_name: str) -> bool:
    """Check if model name is an Azure deployment (not a factory model)."""
    model_name = model_name.lower()
    if model_name in _MODEL_FACTORY_MODELS:
        return False
    azure_patterns = ['o1', 'gemini', 'claude', 'aws-nova', 'gpt-', 'claude-', 'gemini-']
    return any(pattern in model_name for pattern in azure_patterns)


# Azure model mapping: (prefix, variant_keyword) -> ModelClass
# Order matters: more specific patterns first
_AZURE_MODEL_PATTERNS = [
    # GPT models
    ('o1', None, ModelClass.GPT_O3_MINI),
    ('gpt-4o', None, ModelClass.GPT_4O_1120),
    ('gpt-4', None, ModelClass.GPT_4_TURBO),
    ('gpt-41', None, ModelClass.GPT_41_0414),
    # Gemini models (check variant first)
    ('gemini-2.5', 'pro', ModelClass.GEMINI_2_5_PRO),
    ('gemini-2.5', None, ModelClass.GEMINI_2_5_FLASH),
    ('gemini-2.0', 'pro', ModelClass.GEMINI_2_5_PRO),
    ('gemini-2.0', None, ModelClass.GEMINI_2_5_FLASH),
    ('gemini', None, ModelClass.GEMINI_2_5_FLASH),
    # Claude models (check variant first)
    ('claude-4', 'sonnet', ModelClass.CLAUDE_4_SONNET),
    ('claude-4', None, ModelClass.CLAUDE_4_OPUS),
    ('claude-3.5', 'sonnet', ModelClass.CLAUDE_3_7_SONNET),
    ('claude-3.5', None, ModelClass.CLAUDE_3_5_HAIKU),
    ('claude-3', 'sonnet', ModelClass.CLAUDE_3_SONNET),
    ('claude-3', None, ModelClass.CLAUDE_3_HAIKU),
    ('claude', None, ModelClass.CLAUDE_3_SONNET),
    # AWS Nova models (check variant first)
    ('aws-nova-1', 'pro', ModelClass.AWS_NOVA_1_PRO),
    ('aws-nova-1', 'lite', ModelClass.AWS_NOVA_1_LITE),
    ('aws-nova-1', None, ModelClass.AWS_NOVA_1_MICRO),
]


def get_model_class_for_azure_model(model_name: str) -> ModelClass:
    """Determine ModelClass for Azure deployment using pattern matching."""
    for prefix, variant, model_class in _AZURE_MODEL_PATTERNS:
        if model_name.startswith(prefix):
            # If variant specified, check if present in model name
            if variant is None or variant in model_name:
                return model_class

    return ModelClass.UNSPECIFIED


def get_model(model_name: str) -> ModelFactory | AzureChatModel:
    """
    Get model instance (factory or Azure deployment).

    Args
    ----
        model_name: Model name (case-insensitive)

    Returns
    -------
        ModelFactory or AzureChatModel instance

    Raises
    ------
        ValueError: If model is not supported
    """
    model_name = model_name.lower()

    # Return factory model if available
    if model_name in _MODEL_FACTORY_MODELS:
        return _MODEL_FACTORY_MODELS[model_name]

    # Create Azure deployment model
    if is_azure_model(model_name):
        return AzureChatModel(
            model_name=model_name,
            azure_deployment=model_name,
            model_class=get_model_class_for_azure_model(model_name),
            api_version='2024-10-21',
        )

    # Model not found
    available_factory = ', '.join(sorted(_MODEL_FACTORY_MODELS.keys()))
    raise ValueError(
        f'Model "{model_name}" not supported.\n'
        f'Available: {available_factory}\n'
        f'For Azure: use deployment name (e.g., "gemini-2.0-pro-exp-02-05")'
    )
