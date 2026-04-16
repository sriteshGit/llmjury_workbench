"""Load `.env` before LiteLLM reads API keys (standalone / Streamlit / subprocess eval)."""

from __future__ import annotations

import os
from pathlib import Path


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def load_llmjury_env(repo_root: Path | None = None) -> Path | None:
    """
    Load environment variables from the first existing file among:

    1. ``LLMJURY_ENV_FILE`` (explicit path)
    2. ``<repo_root>/.env`` when ``repo_root`` is passed (e.g. workbench subprocess)
    3. ``<package_repo_root>/.env`` — parent of the ``llmjury`` package (editable install layout)
    4. ``./.env`` under the current working directory

    Returns the path loaded, or ``None`` if no file was found.
    ``python-dotenv`` is optional at runtime only for this function; it is a declared dependency.
    """
    from dotenv import load_dotenv

    candidates: list[Path] = []
    env_file = os.environ.get('LLMJURY_ENV_FILE', '').strip()
    if env_file:
        candidates.append(Path(env_file).expanduser())

    if repo_root is not None:
        candidates.append(Path(repo_root) / '.env')

    # .../llmjury_workbench/llmjury/env_bootstrap.py -> repo = parent of llmjury/
    pkg_dir = Path(__file__).resolve().parent
    candidates.append(pkg_dir.parent / '.env')

    candidates.append(Path.cwd() / '.env')

    for path in _unique_paths(candidates):
        if path.is_file():
            load_dotenv(path, override=False)
            return path

    load_dotenv(override=False)
    return None
