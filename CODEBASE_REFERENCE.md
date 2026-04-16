# LLMJury Workbench — codebase reference

This document indexes the repository for maintainers: what each major area does, how execution flows from the UI to LLM calls, and where to change behavior. For user-facing setup and workflows, see [README.md](README.md). For historical UI architecture notes, see [OVERVIEW.md](OVERVIEW.md). For deployment, see [DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md).

---

## What this repository is

A **standalone** Python package (`llmjury`) plus a **Streamlit** workbench (`app.py`) for running multi-model, multi-criterion LLM evaluations, persisting results (JSON / Excel), and analyzing or comparing runs. LLM access is through **LiteLLM** and provider API keys in the environment (loaded early via `python-dotenv`).

---

## Top-level layout

| Path | Role |
|------|------|
| `app.py` | Streamlit entry: loads env, sets page config, hosts four tabs. |
| `pyproject.toml` | Package metadata, dependencies, setuptools package data (includes `llmjury/data/prompts/**` and `prompt_versions.json`). |
| `Makefile` | `install`, `verify`, `run`, Docker helpers, background run targets. |
| `llmjury/` | Core evaluation library, prompt assets, runtime abstractions. |
| `runners/` | CLI and callable `llm_evaluator()` used by automation and the workbench. |
| `components/` | Streamlit tabs: runner, dashboard, comparison, getting started. |
| `utils/` | Shared helpers for loading data, AgGrid, Plotly charts, conversions. |
| `scripts/verify_setup.py` | Sanity check for imports and optional one-shot API verification. |

---

## Application flow (Streamlit)

1. **`app.py`** calls `load_llmjury_env()` from `llmjury.env_bootstrap` before other imports so LiteLLM sees API keys from `.env` (or `LLMJURY_ENV_FILE`).
2. Tabs (in order): **Run Evaluation** → **Dashboard** → **Comparison** → **Getting Started**, implemented in `components/`.
3. **Run Evaluation** (`components/evaluation_runner_unified.py`):
   - Collects input (dashboard-derived JSON, uploaded JSON, folder path, or ad-hoc fields), optional conversion via `utils/data_converter.py`, writes inputs under the user-chosen output directory.
   - On run, writes a small **`run_eval.py`** under that output directory, then starts **`subprocess.Popen([sys.executable, str(script_file)], ...)`** with stdout streamed into the UI. The generated script inserts the repo root on `sys.path`, calls `load_llmjury_env(repo_root=...)`, `chdir`s to the output directory, and invokes **`runners.run_llmjury_evaluator.llm_evaluator(...)`** programmatically.
   - The UI also shows a **CLI-style preview** of `python runners/run_llmjury_evaluator.py ...`; that mirrors what you can run manually from a shell. The live run path is the generated `run_eval.py`, not necessarily a direct CLI invocation.
4. **Dashboard** (`components/unified_dashboard.py`): loads Excel/JSON via `utils/data_loader.py`, AgGrid via `utils/aggrid_helper.py`; can push selected rows into session state for re-analysis in the runner.
5. **Comparison** (`components/comparison.py`): multiple result files, Plotly charts from `utils/visualizations.py`.

---

## Evaluation stack (`llmjury/`)

High-level pipeline:

**Input JSON (or folder of JSON)** → **`Connector` / `Session`** (read sections) → **`LLMJuryEvaluator`** (`llmjury_evaluator.py`, extends **`Operator`**) → per-section work in **`llm_jury_per_section.py`** → prompts from loaders / **`llmjury/data/prompts/`** → **`LLMWrapper` / `chat_invoker.py`** (LiteLLM `completion`) → results → **`LLMJuryResultsTransformer`** → **`LLMJuryExcelPersister`** / reporting (**`report_generator.py`**, optional **`meta_analyzer.py`**).

| Module | Purpose |
|--------|---------|
| `constants.py` | `EvaluationMode` (`metrics`, `question_answer`, `comparison`), prompt dir names, enums for prompt families, sheet names. |
| `model_factory.py` | Maps friendly aliases (e.g. `gpt_4o_mini`, `grok_mini`) to LiteLLM model ids; `get_model()`, `ChatModelSpec`. |
| `chat_invoker.py` | LiteLLM-backed `LLMWrapper`; message format normalization. |
| `env_bootstrap.py` | Resolves and loads `.env` from explicit path, repo root, package parent, or cwd. |
| `runtime/connector.py`, `session.py`, `operator.py` | Dataflow primitives: streaming JSON sections, parallel `Operator` execution. |
| `llmjury_evaluator.py` | Orchestrates evaluation across models and sections; parallelism defaults from CPU count (capped). |
| `llm_jury_per_section.py` | Per-section scoring logic for the active mode. |
| `llm_jury_prompt_loader.py`, `llm_jury_criteria_definition_loader.py`, `prompt_selector.py`, `prompt_version_config.py`, `support/prompt_configuration_manager.py` | Prompt assembly and versioning; criteria definition JSON under `data/prompts/criteriaDefinitionLLMJURY/`. |
| `field_mappings.py`, `mode_config.py` | Field / mode configuration for different content shapes. |
| `excel_persister.py`, `report_generator.py` | Excel output and report sheets. |
| `llm_jury_results_transformer.py` | Normalizes raw outputs for persistence. |
| `meta_analyzer.py` | Optional meta-analysis over aggregated results. |

Package data: **`llmjury/data/prompts/`** holds versioned prompt templates and configs (`llmJURY/` for metrics, Q&A, comparison; `criteriaDefinitionLLMJURY/` per criterion). **`llmjury/prompt_versions.json`** ties version ids to on-disk prompt paths.

---

## Runners (`runners/`)

| File | Role |
|------|------|
| `run_llmjury_evaluator.py` | **`llm_evaluator(...)`**: main programmatic API (paths, criteria, models, mode, custom prompt, meta flags). Also a **`argparse`** CLI when executed as `__main__` — processes `--eval_json_path` (file or directory), writes JSON + Excel via the same stack. |
| `transform_llmjury_results.py` | Transforms existing JSON results to Excel-only (no new LLM calls). |

---

## Session state (Workbench)

The UI relies on `st.session_state` for persistence across reruns. Non-exhaustive keys (see also [OVERVIEW.md](OVERVIEW.md)):

- Dashboard: `dashboard_data`, `dashboard_filename`, selection / re-analysis payloads.
- Runner: `last_eval_results`, `eval_data_source`, `converted_data_path`, `evaluation_running`, folder vs upload flags.
- Comparison: datasets loaded for charting.

When extending the UI, avoid duplicate widget keys (a common Streamlit pitfall).

---

## Dependencies (from `pyproject.toml`)

Runtime highlights: `streamlit`, `pandas`, `numpy`, `plotly`, `streamlit-aggrid`, `openpyxl`, `langchain-core`, `pydantic`, `litellm`, `python-dotenv`. Dev: `pytest`, `black`, `ruff`.

---

## Common extension points

- **New model alias**: add to `_ALIASES` in `llmjury/model_factory.py` and document required env vars (provider docs / LiteLLM).
- **New criterion or prompt version**: add JSON under `llmjury/data/prompts/` and wire through `prompt_versions.json` / prompt loaders as needed.
- **New tab or layout**: `app.py` + new module under `components/`.
- **Batch / CI**: call `python runners/run_llmjury_evaluator.py` with the same flags as the CLI preview, or import `llm_evaluator` from a trusted script with explicit paths.

---

## Version

Workbench package version is declared in `pyproject.toml` (`0.1.0` at time of writing). The evaluator class exposes `LLMJuryEvaluator.VERSION` in code (`llmjury_evaluator.py`).

---

## Document map

| Document | Audience |
|----------|----------|
| [README.md](README.md) | Install, `.env`, features, JSON formats, Make/Docker. |
| [OVERVIEW.md](OVERVIEW.md) | Streamlit architecture, session state, design rationale (note: subprocess description centers on the runner; the workbench may generate a small `run_eval.py` that calls `llm_evaluator` — see **Application flow** above). |
| [llmjury/README.md](llmjury/README.md) | Criteria semantics and CLI-oriented usage of the library. |
| This file | Code navigation and end-to-end technical index. |
