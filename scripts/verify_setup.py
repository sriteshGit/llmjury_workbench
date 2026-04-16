#!/usr/bin/env python3
"""Verify the repo runs independently: imports, .env loading, optional one-shot LLM call."""

from __future__ import annotations

import argparse
import importlib
import py_compile
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify LLMJury workbench / runner setup')
    parser.add_argument(
        '--with-api',
        action='store_true',
        help='Call LiteLLM once using LLMJURY_VERIFY_MODEL (requires matching API key in .env)',
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo))

    from llmjury.env_bootstrap import load_llmjury_env

    loaded = load_llmjury_env(repo_root=repo)
    print(f'✓ Repo root: {repo}')
    print(f'✓ load_llmjury_env: {loaded or "(no .env file found; using process env only)"}')

    for mod in (
        'llmjury.runtime',
        'llmjury.chat_invoker',
        'llmjury.model_factory',
        'llmjury.llmjury_evaluator',
    ):
        importlib.import_module(mod)
        print(f'✓ import {mod}')

    # Syntax-check runners without importing them (avoids pulling pandas when only testing core).
    for script in ('run_llmjury_evaluator.py', 'transform_llmjury_results.py'):
        path = repo / 'runners' / script
        py_compile.compile(str(path), doraise=True)
        print(f'✓ py_compile runners/{script}')

    if args.with_api:
        import os

        from litellm import completion

        model = os.environ.get('LLMJURY_VERIFY_MODEL', '').strip()
        if not model:
            print('✗ --with-api requires LLMJURY_VERIFY_MODEL in the environment or .env', file=sys.stderr)
            return 2
        print(f'→ completion probe model={model!r} ...')
        resp = completion(
            model=model,
            messages=[{'role': 'user', 'content': 'Reply with exactly: OK'}],
            max_tokens=8,
            temperature=0,
        )
        text = resp.choices[0].message.content or ''
        print(f'✓ API response snippet: {text[:200]!r}')

    print('✓ verify_setup completed successfully')
    print('  Tip: use a project venv to avoid host numpy/pandas conflicts: python3 -m venv .venv && .venv/bin/pip install -e .')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
