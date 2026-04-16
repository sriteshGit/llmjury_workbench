from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class Operator:
    """Minimal operator base: name + optional parallelism for LLMJuryEvaluator."""

    def __init__(self, name: str | None = None, parallelism: int | None = None) -> None:
        self.name = name
        self.parallelism = parallelism if parallelism and parallelism > 0 else 1
        self._executor: ThreadPoolExecutor | None = None

    def submit_task(
        self,
        fn: Callable[..., Any],
        *args: Any,
        abort_on_error: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Run fn in a thread pool (used by LLMJuryEvaluator). Returns a Future-like handle."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.parallelism)
        return self._executor.submit(fn, *args, **kwargs)

    def _shutdown_executor(self) -> None:
        ex = getattr(self, '_executor', None)
        if ex is not None:
            ex.shutdown(wait=True, cancel_futures=False)
            self._executor = None
