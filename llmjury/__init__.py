"""LLMJury: LLM-based multi-criteria evaluation (standalone package)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('llmjury-workbench')
except PackageNotFoundError:
    __version__ = '0.0.0'
