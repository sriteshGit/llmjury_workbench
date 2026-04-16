# ⚖️ LLMJury Workbench

**Interactive platform for LLM-based evaluations with comprehensive dashboards, evaluation runners, and model comparison tools.**

This repository is a **standalone** LLMJury evaluation stack and Streamlit workbench. It bundles the `llmjury` Python package, prompt assets under `llmjury/data/prompts/`, and CLI runners under `runners/`.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- API keys for at least one [LiteLLM-supported provider](https://docs.litellm.ai/docs/providers). Keys are read from the process environment; the repo loads a **repo-root `.env`** automatically (via `python-dotenv`).

### Credentials (`.env`)

1. Copy the template and edit (never commit `.env`; it is gitignored):

```bash
cp .env.example .env
```

2. Uncomment and set keys for the providers you use, for example:

- **xAI Grok** (including free-tier credits from [console.x.ai](https://console.x.ai)): `XAI_API_KEY` — then choose models such as `grok_mini`, `grok_free`, or `xai/grok-3-mini` in the UI or CLI.
- **Groq** ([console.groq.com](https://console.groq.com/keys)): `GROQ_API_KEY` — e.g. alias `groq_fast` → `groq/llama-3.1-8b-instant`, or `groq_llama_70b` / `groq/llama-3.3-70b-versatile` for **Llama 3.3 70B** (this is not xAI Grok; Grok needs `XAI_API_KEY`).
- **OpenAI**: `OPENAI_API_KEY` — models like `gpt_4o_mini`.

3. Optional env vars:

- `LLMJURY_DEFAULT_MODELS` — comma-separated model names for the workbench multiselect default (e.g. `grok_mini,gpt_4o_mini`).
- `LLMJURY_ENV_FILE` — absolute path to an env file if not using `./.env`.
- `LLMJURY_VERIFY_MODEL` — used by `make verify-api` (e.g. `xai/grok-3-mini`).

### Installation & Running

```bash
# Navigate to workbench directory
cd llmjury_workbench

# Setup (first time only - installs uv + dependencies)
make setup

# Or just install dependencies
make install

# Recommended: isolated venv (avoids host numpy/pandas conflicts)
python3 -m venv .venv && .venv/bin/pip install -e .

# Confirm imports + .env loading (no network; uses .venv/bin/python if present)
make verify

# Run the workbench
make run
```

The workbench will be available at `http://localhost:8501`

### Alternative: Using the Shell Script

```bash
chmod +x start_workbench.sh
./start_workbench.sh
```

---

## 🎯 Features

### 📊 Dashboard
- Load and analyze evaluation results (Excel/JSON)
- Interactive filtering and sorting
- Color-coded score visualization
- Export selected data
- One-click re-analysis

### 🚀 Run Evaluation
**Flexible Input Options:**
- **Dashboard Data**: Re-analyze loaded results
- **Upload JSON**: Upload evaluation files or specify folder path
- **Ad-hoc Input**: Create evaluations with text inputs

**Evaluation Features:**
- Multi-model evaluation (GPT-4, Claude, Gemini, etc.)
- Multiple criteria selection (accuracy, clarity, conciseness, etc.)
- Custom prompts (inline)
- Real-time logs
- Persistent results

**Results Management:**
- Download Excel results
- Download JSON results
- Download execution logs
- Load results directly in dashboard
- Copy output path

### 📈 Comparison
- Side-by-side model comparison
- Interactive charts (bar, box plot, heatmap, scatter)
- Response-level comparison
- Statistical insights

---

## 📁 Project Structure

```
llmjury_workbench/
├── .env.example                    # Template for API keys (copy to .env)
├── scripts/verify_setup.py         # Independent sanity check (make verify)
├── app.py                          # Main Streamlit application
├── llmjury/                        # Evaluation library
│   ├── data/prompts/llmJURY/       # Prompt templates + configs for metrics / Q&A / comparison / meta
│   └── ...
├── runners/
│   ├── run_llmjury_evaluator.py    # CLI: full evaluate → JSON + Excel
│   └── transform_llmjury_results.py # CLI: JSON results → Excel only
├── components/
│   ├── unified_dashboard.py        # Dashboard tab
│   ├── evaluation_runner_unified.py # Evaluation runner tab
│   └── comparison.py               # Comparison tab
├── utils/
│   ├── data_loader.py              # Data loading utilities
│   ├── data_converter.py           # Data format conversion
│   ├── aggrid_helper.py            # AgGrid configuration
│   └── visualizations.py           # Plotly chart creation
├── temp_evaluations/               # Output directory (gitignored)
├── Makefile                        # Build & run commands
├── pyproject.toml                  # Project configuration & dependencies
├── Dockerfile                      # Container definition
├── docker-compose.yml              # Multi-container setup
└── README.md                       # This file
```

---

## 🐳 Docker Deployment

Build context is **this repository root** (the image installs `llmjury`, `runners`, and the Streamlit app together).

### Build Docker Image

```bash
# Using Make (recommended)
make docker-build

# Or manually from the repo root:
docker build -t llmjury-workbench:0.1.0 .
```

### Run with Docker

```bash
# Single container
make docker-run

# Or with Docker Compose
make docker-up

# Stop services
make docker-down
```

**Image size:** depends on base image and dependency wheels (standalone build context).

### Environment Variables

Set these before running:

```bash
export OPENAI_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here
```

Or create a `.env` file:
```bash
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
STREAMLIT_SERVER_PORT=8501
OUTPUT_DIR=./temp_evaluations
```

---

## 🛠️ Development

### Available Make Commands

```bash
make help              # Show all available commands
make setup             # Install uv + dependencies (first time)
make install           # Install dependencies using uv
make run               # Run the Streamlit workbench
make clean             # Clean cache/temp files
make test              # Run tests
make lint              # Run linting
make docker-build      # Build Docker image
make docker-run        # Run Docker container
make docker-up         # Start services with Docker Compose
make docker-down       # Stop Docker services
```

### Dependencies

Core dependencies:
- `streamlit` - Web interface
- `pandas` - Data manipulation
- `plotly` - Interactive visualizations
- `streamlit-aggrid` - Excel-like data tables
- `openpyxl` - Excel file handling

---

## 🔄 Common Workflows

### View & Re-analyze Existing Results
```
Dashboard → Load results → Filter → Select rows → Re-analyze → Run → View results
```

### Fresh Evaluation from Files
```
Run Evaluation → Upload JSON → Configure → Run → Download results
```

### Quick Test with Ad-hoc Input
```
Run Evaluation → Ad-hoc Input → Paste text → Configure → Run
```

---

## 📖 Usage Guide

### 1. Dashboard Tab

**Load Results:**
- Upload Excel/JSON file
- Paste file path
- Or load from evaluation runner

**Analyze:**
- Filter by model, criteria, scores
- Sort columns
- View statistics
- Export filtered data

**Actions:**
- Select rows → Click "Re-analyze" → Automatically switches to Runner tab

### 2. Run Evaluation Tab

**Input Data (Choose One):**

**a) Dashboard Data**
- Automatically available if data loaded in dashboard
- Shows conversion preview
- One-click use

**b) Upload JSON**
- Upload single/multiple JSON files
- Or specify folder path containing JSONs
- Supports batch processing

**c) Ad-hoc Input**
- Enter `source` (required)
- Enter `response` (required)
- Optionally add `question`, `response2`
- Optionally add `additional_data` (JSON format)

**Configure:**
- Select evaluation mode (metrics/pairwise)
- Choose models
- Select criteria
- Optionally add custom prompt (use variables: `{source}`, `{response}`, `{question}`, `{criteria_name}`, `{additional_data}`)
- Set result name
- Set output location

**Custom Prompt Example:**
```
Evaluate for {criteria_name}:

Source: {source}
Response: {response}

Rate 1-5 with detailed reasoning.
```

**Execute & Download:**
- Click "Run Evaluation"
- Watch live logs
- Download Excel, JSON, Logs
- Load in Dashboard
- Copy output path

### 3. Comparison Tab

**Load Results:**
- Upload 2+ result files
- Select models to compare

**Visualize:**
- Bar charts (average scores)
- Box plots (distributions)
- Heatmaps (model-criteria matrix)
- Scatter plots (correlations)

**Compare Responses:**
- Select specific entries
- View side-by-side responses
- See score differences

---

## 🔧 Configuration

### Custom Output Directory

By default, results are saved to `temp_evaluations/`. Change this in the evaluation runner.

### API Keys

Set environment variables or configure in your shell:

```bash
# ~/.bashrc or ~/.zshrc
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

### Streamlit Configuration

Create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"

[server]
port = 8501
```

---

## 🚢 Deployment

### Local Development

```bash
make run
```

### Production (Docker)

```bash
# Build and run
make docker-build
make docker-compose-up

# Access at http://your-server:8501
```

### Cloud Deployment

The workbench can be deployed to:
- AWS ECS/Fargate
- Google Cloud Run
- Azure Container Instances
- Kubernetes clusters

See `DEPLOYMENT_STRATEGY.md` for detailed instructions.

---

## 📊 Data Formats

### Input JSON Format

```json
{
  "entry_1": {
    "source": "Original text or query",
    "response": "AI-generated response",
    "question": "Optional question",
    "response2": "Optional second response for pairwise",
    "additional_data": {
      "key": "value"
    }
  }
}
```

### Output Excel/JSON

Results include:
- Original source/response
- Scores for each criterion
- Model information
- Timestamps
- Any additional metadata

---

## 🤝 Contributing

1. Follow existing code structure
2. Test all changes
3. Update documentation
4. Use `make clean` before committing

---

## 📝 License

Specify a license for your distribution (this template does not ship a default `LICENSE` file).

---

## 💡 Tips

- **Performance**: Use smaller datasets for initial testing
- **API Costs**: Monitor your API usage, especially with multiple models
- **Results**: Results persist across sessions via session state
- **Remote Access**: Download buttons work even in Docker/remote deployments
- **Batch Processing**: Upload multiple JSONs or use folder path for efficiency
- **Re-analysis Workflow**: Use re-analysis for faster iteration when refining prompts/criteria
- **Custom Prompts**: Save your custom prompts as `.txt` files for reuse
- **Clean Up**: Run `make clean` regularly to remove temporary files
- **Selective Export**: Export only selected rows from dashboard for targeted re-analysis

---

## 🐛 Troubleshooting

**Workbench won't start:**
- Check Python version (3.10+)
- Verify all dependencies installed: `make install` or `uv pip install -e .`

**API Errors:**
- Verify API keys are set
- Check network connectivity
- Ensure sufficient API credits

**Docker Issues:**
- Ensure Docker is running
- Check port 8501 is available
- Verify volume mounts for results

**Results Not Persisting:**
- Results are stored in session state
- Use download buttons to save locally
- Check output directory permissions

---

## 📧 Support

For issues related to:
- **Workbench UI**: Check this README
- **LLMJury Evaluation**: See `llmjury/README.md` and runner docstrings under `runners/`
- **API Issues**: Consult provider documentation

---

## 📚 Documentation

- **README.md** (this file) - Quick start and usage
- **CODEBASE_REFERENCE.md** - Codebase index, module roles, and execution flow for maintainers
- **OVERVIEW.md** - Technical architecture and design decisions
- **DEPLOYMENT_STRATEGY.md** - Detailed deployment guide

---

**Version:** 2.0.0
**Built with ❤️ for efficient LLM evaluation**
