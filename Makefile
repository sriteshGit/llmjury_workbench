# LLMJury Workbench - Makefile

.PHONY: help install run run-detached run-daemon stop kill-all status logs clean test all

# Default target
.DEFAULT_GOAL := help

# Configuration
PIDFILE := .workbench.pid
LOGFILE := .workbench.log

help: ## Show available commands
	@echo "LLMJury Workbench - Available Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'
	@echo ""

install: ## Install dependencies with uv
	@echo "Installing dependencies..."
	@command -v uv >/dev/null 2>&1 || { echo "Error: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	uv pip install -e .
	@echo "✅ Dependencies installed"

run: ## Start the workbench (foreground)
	@echo "🚀 Starting LLMJury Workbench (foreground)..."
	@if [ ! -f "app.py" ]; then echo "❌ Error: app.py not found"; exit 1; fi
	@echo "💡 Tip: Use 'make run-detached' for background mode with auto-restart"
	@streamlit run app.py

run-detached: ## Start in background with auto-restart on crash
	@echo "🚀 Starting LLMJury Workbench (detached with auto-restart)..."
	@if [ ! -f "app.py" ]; then echo "❌ Error: app.py not found"; exit 1; fi
	@if [ -f "$(PIDFILE)" ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "⚠️  Workbench is already running (PID: $$(cat $(PIDFILE)))"; \
		echo "   Use 'make stop' to stop it first"; \
		exit 1; \
	fi
	@bash -c '\
		while true; do \
			echo "$$(date): Starting LLMJury Workbench..." >> $(LOGFILE); \
			streamlit run app.py >> $(LOGFILE) 2>&1; \
			EXIT_CODE=$$?; \
			if [ $$EXIT_CODE -eq 0 ]; then \
				echo "$$(date): Graceful exit, stopping auto-restart" >> $(LOGFILE); \
				break; \
			fi; \
			echo "$$(date): Crashed (exit code: $$EXIT_CODE), restarting in 5s..." >> $(LOGFILE); \
			sleep 5; \
		done \
	' & echo $$! > $(PIDFILE)
	@echo "✅ Started in background with auto-restart (PID: $$(cat $(PIDFILE)))"
	@echo "📋 Logs: make logs"
	@echo "🛑 Stop: make stop"
	@echo "📊 Status: make status"

run-daemon: ## Start in background (simple, no auto-restart)
	@echo "🚀 Starting LLMJury Workbench (simple daemon)..."
	@if [ ! -f "app.py" ]; then echo "❌ Error: app.py not found"; exit 1; fi
	@if [ -f "$(PIDFILE)" ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "⚠️  Workbench is already running (PID: $$(cat $(PIDFILE)))"; \
		echo "   Use 'make stop' to stop it first"; \
		exit 1; \
	fi
	@nohup streamlit run app.py > $(LOGFILE) 2>&1 & echo $$! > $(PIDFILE)
	@echo "✅ Started in background (PID: $$(cat $(PIDFILE)))"
	@echo "⚠️  Note: Won't auto-restart on crash. Use 'make run-detached' for auto-restart"
	@echo "📋 Logs: make logs"
	@echo "🛑 Stop: make stop"

stop: ## Stop the detached workbench
	@if [ ! -f "$(PIDFILE)" ]; then \
		echo "⚠️  No PID file found"; \
		echo "🔍 Checking for orphaned streamlit processes..."; \
		pkill -f "streamlit run app.py" 2>/dev/null && echo "✅ Killed orphaned processes" || echo "   No orphaned processes found"; \
		exit 0; \
	fi
	@PID=$$(cat $(PIDFILE)); \
	if kill -0 $$PID 2>/dev/null; then \
		echo "🛑 Stopping workbench (PID: $$PID)..."; \
		echo "   Killing process tree..."; \
		pkill -P $$PID 2>/dev/null || true; \
		kill $$PID 2>/dev/null || true; \
		sleep 2; \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⚠️  Process still running, force killing..."; \
			pkill -9 -P $$PID 2>/dev/null || true; \
			kill -9 $$PID 2>/dev/null || true; \
			sleep 1; \
		fi; \
		pkill -f "streamlit run app.py" 2>/dev/null || true; \
		echo "✅ Stopped"; \
	else \
		echo "⚠️  Process not running (stale PID)"; \
		echo "🔍 Checking for orphaned streamlit processes..."; \
		pkill -f "streamlit run app.py" 2>/dev/null && echo "✅ Killed orphaned processes" || echo "   No orphaned processes found"; \
	fi
	@rm -f $(PIDFILE)

kill-all: ## Force kill all streamlit processes (use if stop fails)
	@echo "💀 Force killing ALL streamlit processes..."
	@pkill -9 -f "streamlit run app.py" 2>/dev/null && echo "✅ Killed all streamlit processes" || echo "⚠️  No streamlit processes found"
	@rm -f $(PIDFILE)
	@echo "✅ Cleanup complete"

status: ## Check if workbench is running
	@if [ ! -f "$(PIDFILE)" ]; then \
		echo "❌ Workbench is not running (no PID file)"; \
		exit 1; \
	fi
	@PID=$$(cat $(PIDFILE)); \
	if kill -0 $$PID 2>/dev/null; then \
		echo "✅ Workbench is running (PID: $$PID)"; \
		echo "🌐 URL: http://localhost:8501"; \
		ps -p $$PID -o pid,etime,command; \
	else \
		echo "❌ Workbench is not running (stale PID file)"; \
		rm -f $(PIDFILE); \
		exit 1; \
	fi

logs: ## View logs (tail -f)
	@if [ ! -f "$(LOGFILE)" ]; then \
		echo "⚠️  No log file found"; \
		exit 1; \
	fi
	@echo "📋 Tailing logs (Ctrl+C to exit)..."
	@tail -f $(LOGFILE)

clean: ## Clean cache and temporary files
	@echo "Cleaning..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache 2>/dev/null || true
	rm -f $(PIDFILE) $(LOGFILE) 2>/dev/null || true
	@echo "✅ Cleaned"

test: ## Run tests
	@echo "Running tests..."
	@command -v pytest >/dev/null 2>&1 && pytest tests/ || echo "No tests configured"

setup: ## Initial setup (install uv + dependencies)
	@echo "Setting up..."
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	$(MAKE) install
	@echo "✅ Setup complete! Run 'make run' to start"

# Docker commands
docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t llmjury-workbench:0.1.0 .
	@echo "✅ Image built"

docker-run: ## Run Docker container
	docker run -d --name llmjury-workbench -p 8501:8501 llmjury-workbench
	@echo "✅ Running at http://localhost:8501"

docker-stop: ## Stop Docker container
	docker stop llmjury-workbench 2>/dev/null || true
	docker rm llmjury-workbench 2>/dev/null || true

docker-up: ## Start with docker-compose
	docker-compose up -d
	@echo "✅ Running at http://localhost:8501"

docker-down: ## Stop docker-compose
	docker-compose down

all: clean install ## Clean and install
	@echo "✅ Ready"
