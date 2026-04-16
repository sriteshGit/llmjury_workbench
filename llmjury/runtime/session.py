from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def Session(name: str = 'LLMJURY') -> Iterator[Any]:
    """No-op session context (replaces venice.core.Session)."""
    yield None
