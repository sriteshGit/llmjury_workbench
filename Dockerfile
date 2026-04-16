# LLMJury Workbench — standalone image
FROM python:3.11-slim

LABEL maintainer="LLMJury Workbench"
LABEL description="LLMJury Workbench"
LABEL version="2.1.0"

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY llmjury ./llmjury
COPY components ./components
COPY utils ./utils
COPY runners ./runners
COPY app.py __version__.py ./
COPY .streamlit ./.streamlit

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

RUN mkdir -p temp_evaluations

ENV PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
