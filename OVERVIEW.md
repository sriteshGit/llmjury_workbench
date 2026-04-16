# LLMJury Workbench - Technical Overview

## What It Is

Interactive web tool for running and analyzing LLMJury evaluations. Built with Streamlit for simplicity and speed.

## Architecture

The LLMJury Workbench is built as a modular Streamlit application that provides a complete end-to-end solution for LLM evaluation.

### High-Level Flow

```
Workbench (UI)  →  subprocess  →  runners/run_llmjury_evaluator.py  →  llmjury + LiteLLM (public provider APIs)
  Streamlit           Python         LLMJury Runner           Framework
```

**Key insight:** Workbench only provides UI. Actual evaluation runs via subprocess calling the existing runner.

### Core Components

```
app.py
├── Dashboard Tab (unified_dashboard.py)
│   ├── Data Loading (file upload, path input)
│   ├── Interactive Table (AgGrid)
│   ├── Filtering & Selection
│   └── Re-analysis Trigger
│
├── Evaluation Runner Tab (evaluation_runner_unified.py)
│   ├── Input Data Section (tabs)
│   │   ├── Dashboard Data (converted format)
│   │   ├── Upload JSON (single/multiple/folder)
│   │   └── Ad-hoc Input (text boxes)
│   ├── Configuration Section
│   │   ├── Mode, Models, Criteria
│   │   ├── Custom Prompts
│   │   └── Output Settings
│   ├── Execution Section
│   │   ├── Subprocess Runner
│   │   └── Real-time Logs
│   └── Results Section
│       ├── Download Buttons (Excel, JSON, Logs)
│       ├── Load in Dashboard
│       └── Copy Path
│
└── Comparison Tab (comparison.py)
    ├── Multi-file Loading
    ├── Visualizations (Plotly)
    ├── Side-by-side Comparison
    └── Statistical Analysis
```

### Utility Modules

- **data_loader.py**: Load Excel/JSON results, compute statistics
- **data_converter.py**: Convert dashboard exports to LLMJury format
- **aggrid_helper.py**: Configure interactive data tables
- **visualizations.py**: Create Plotly charts (bar, box, heatmap, etc.)

---

## Key Design Decisions

### 1. Unified Evaluation Runner

**Problem**: Previously had separate UIs for fresh evaluation and re-analysis.

**Solution**: Single `evaluation_runner_unified.py` with tabbed input section:
- Dashboard Data (for re-analysis)
- Upload JSON (for fresh evaluation from files)
- Ad-hoc Input (for quick testing)

**Benefits**:
- Consistent UX
- Reduced code duplication
- Easier maintenance

### 2. Session State for Persistence

**Problem**: Streamlit reruns lose data, causing results to disappear after button clicks.

**Solution**: Store critical data in `st.session_state`:
- `last_eval_results`: Paths, logs, metadata
- `dashboard_data`: Loaded DataFrame
- `eval_data_source`: Track where data came from

**Benefits**:
- Results persist across reruns
- Download buttons work multiple times
- Seamless navigation between tabs

### 3. Subprocess for Evaluation

**Problem**: Long-running evaluations block UI and can't show progress.

**Solution**: Run `run_llmjury_evaluator.py` as subprocess:
- Read stdout in real-time
- Display logs as they appear
- Non-blocking execution

**Benefits**:
- Responsive UI during evaluation
- User can see progress
- Clean separation of concerns

### 4. Multi-stage Docker Build

**Problem**: Docker images were large when they bundled a large parent monorepo instead of this app only.

**Solution**: Multi-stage build:
1. Builder stage: Install dependencies
2. Runtime stage: Copy only necessary files

**Benefits**:
- Smaller final image
- Faster deployments
- Reduced attack surface

---

## Data Flow

### Dashboard → Re-analysis Flow

```
1. User loads results in Dashboard
   ↓
2. User selects rows, clicks "Re-analyze"
   ↓
3. Selected data stored in session_state
   ↓
4. Auto-navigate to Runner tab
   ↓
5. Runner detects dashboard data
   ↓
6. Shows "Dashboard Data" tab with conversion preview
   ↓
7. User configures & runs evaluation
   ↓
8. Results available for download
   ↓
9. Optional: Click "Load in Dashboard" to view results
```

### Upload JSON → Evaluation Flow

```
1. User navigates to Runner tab
   ↓
2. Selects "Upload JSON" tab
   ↓
3. Uploads file(s) or specifies folder
   ↓
4. Data validation & preview
   ↓
5. User configures evaluation
   ↓
6. Click "Run Evaluation"
   ↓
7. Subprocess executes runner script
   ↓
8. Live logs stream to UI
   ↓
9. Results persist in session state
   ↓
10. Download buttons available
```

### Ad-hoc → Evaluation Flow

```
1. User navigates to Runner tab
   ↓
2. Selects "Ad-hoc Input" tab
   ↓
3. Fills text boxes (source, response, etc.)
   ↓
4. Data converted to JSON format
   ↓
5. User configures evaluation
   ↓
6. Evaluation runs
   ↓
7. Results available for download
```

---

## Technology Stack

### Core Technologies

| Component | Technology |
|-----------|------------|
| UI Framework | Streamlit |
| Charts | Plotly |
| Data | Pandas |
| Tables | ag-Grid (streamlit-aggrid) |
| Excel I/O | openpyxl |
| Build | Make + uv |
| Container | Docker |
| CI/CD | GitHub Actions |

### Python Version

- **Minimum**: Python 3.10
- **Recommended**: Python 3.10 or 3.11

### Why These Technologies?

**Why Streamlit?**
- ✅ Pure Python (no HTML/CSS/JS)
- ✅ Fast development
- ✅ Built-in components
- ✅ Easy deployment

**Why Subprocess?**
- ✅ Don't reinvent runner logic
- ✅ Reuse existing battle-tested code
- ✅ Clean separation: UI vs computation

**Why ag-Grid?**
- ✅ Better than native Streamlit table
- ✅ Selection, sorting, filtering
- ✅ Copy/paste support

**Why Multi-Stage Docker?**
- ✅ Smaller image (~600-800MB vs 2-3GB)
- ✅ Faster builds and deploys
- ✅ Production-ready

---

## Performance Optimizations

### 1. Vectorized Operations

In `data_loader.py`:
```python
# Before: Loop through score columns
# After: Use pandas vectorized operations
stats_df = df[score_cols].agg(['mean', 'min', 'max'])
```

**Impact**: 10-100x faster for large datasets

### 2. Dictionary Comprehensions

In `data_converter.py`:
```python
# Before: Multiple loops
# After: Single dict comprehension with filtering
additional_data = {k: str(v) for k, v in row.items() if k not in core_fields}
```

**Impact**: Cleaner code, better performance

### 3. Common Layout Function

In `visualizations.py`:
```python
# Before: Repeated layout code in each function
# After: Single _apply_common_layout() function
```

**Impact**: Reduced code duplication, easier maintenance

---

## State Management

### Session State Keys

```python
# Dashboard
st.session_state.dashboard_data          # DataFrame of results
st.session_state.dashboard_filename      # Name of loaded file

# Evaluation Runner
st.session_state.selected_dashboard_rows # Rows selected for re-analysis
st.session_state.last_eval_results       # Most recent evaluation results
st.session_state.eval_data_source        # 'Dashboard', 'Uploaded', or 'Ad-hoc'

# Comparison
st.session_state.comparison_data         # Loaded comparison datasets
```

### State Lifecycle

1. **Initialization**: Keys created when needed
2. **Update**: Modified on user actions
3. **Persistence**: Maintained across reruns
4. **Cleanup**: Explicitly deleted when user clicks "Clear"

---

## Error Handling

### Common Errors & Solutions

**1. StreamlitDuplicateElementKey**
- **Cause**: Widget with same key rendered twice
- **Solution**: Use unique keys or conditional rendering

**2. File Not Found**
- **Cause**: Invalid path or missing file
- **Solution**: Validate paths before access, show user-friendly errors

**3. API Errors**
- **Cause**: Invalid keys, rate limits, network issues
- **Solution**: Catch exceptions, display helpful messages

**4. Data Format Issues**
- **Cause**: Unexpected JSON structure
- **Solution**: Validate input, provide format examples

---

## Testing Strategy

### Manual Testing Checklist

1. **Dashboard**
   - [ ] Upload Excel file
   - [ ] Upload JSON file
   - [ ] Filter data
   - [ ] Select rows
   - [ ] Click "Re-analyze"

2. **Evaluation Runner**
   - [ ] Use Dashboard Data
   - [ ] Upload single JSON
   - [ ] Upload multiple JSONs
   - [ ] Use folder path
   - [ ] Ad-hoc input
   - [ ] Run evaluation
   - [ ] Download Excel
   - [ ] Download JSON
   - [ ] Download Logs
   - [ ] Load in Dashboard

3. **Comparison**
   - [ ] Load 2 files
   - [ ] View charts
   - [ ] Compare responses

### Automated Testing

Currently minimal. Future additions:
- Unit tests for utility functions
- Integration tests for data flow
- UI tests with Selenium

---

## Deployment Considerations

### Environment Variables

Required:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- (Others as needed)

Optional:
- `PYTHONPATH`: Set to parent directory for imports

### Volume Mounts (Docker)

```yaml
volumes:
  - ./temp_evaluations:/app/temp_evaluations  # Persist results
```

### Port Mapping

```yaml
ports:
  - "8501:8501"  # Streamlit default port
```

### Health Checks

```dockerfile
HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health
```

---

## Future Enhancements

### Potential Features

1. **User Authentication**: Multi-user support
2. **Result History**: Database for long-term storage
3. **Scheduled Evaluations**: Cron-like scheduling
4. **Advanced Analytics**: More statistical tests
5. **Export Options**: PDF reports, CSV exports
6. **Model Registry**: Save/load model configurations
7. **Prompt Library**: Reusable custom prompts
8. **Real-time Collaboration**: Share sessions

### Technical Improvements

1. **Caching**: Use `@st.cache_data` for expensive operations
2. **Async Operations**: Non-blocking API calls
3. **Database Integration**: PostgreSQL for results
4. **Queue System**: Celery for background jobs
5. **Monitoring**: Prometheus metrics
6. **Logging**: Structured logging with levels

---

## Maintenance

### Regular Tasks

- Update dependencies monthly
- Review and fix linter warnings
- Clean up temporary files
- Monitor disk usage (temp_evaluations/)
- Update documentation

### Code Quality

- Follow PEP 8 style guide
- Use type hints where appropriate
- Write docstrings for functions
- Keep functions small and focused
- Avoid deep nesting

---

## Quick Start

```bash
# Local development
make setup
make run

# Docker
make docker-up

# Kubernetes
kubectl apply -f k8s/deployment.yaml
```

---

## Key Principles

1. **Keep it simple** - Don't over-engineer
2. **Reuse existing code** - Subprocess to runner
3. **Single source of truth** - Shared constants in the `llmjury` package
4. **Optimize packaging** - Multi-stage builds
5. **Follow standards** - Make, uv, pyproject.toml

---

## Development Timeline

**v1.0** - Basic viewer and runner
**v2.0** - Unified dashboard, re-analysis, modern build system

**Total effort:** ~10-15 hours
**Status:** Production-ready

---

## Resources

- **Streamlit Docs**: https://docs.streamlit.io
- **Plotly Docs**: https://plotly.com/python
- **AgGrid Docs**: https://github.com/PablocFonseca/streamlit-aggrid
- **Docker Docs**: https://docs.docker.com

---

This overview provides the technical foundation for understanding, maintaining, and extending the LLMJury Workbench.

**For additional details:** See README.md and DEPLOYMENT_STRATEGY.md
