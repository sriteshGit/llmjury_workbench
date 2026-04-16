#!/bin/bash

#   ADOBE CONFIDENTIAL
#   ___________________
#
#   Copyright 2025 Adobe
#   All Rights Reserved.

# LLMJury Workbench Startup Script (Legacy)
# Recommended: Use 'make run' instead

echo "⚠️  This script is deprecated. Please use:"
echo "   make run"
echo ""
echo "For first-time setup:"
echo "   make setup"
echo ""
echo "Continuing with legacy startup..."
echo ""

# Check if running from correct directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: Please run this script from the llmjury_workbench directory"
    echo "   cd llmjury_workbench && ./start_workbench.sh"
    exit 1
fi

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "⚠️  Streamlit not found. Installing dependencies..."
    if command -v uv &> /dev/null; then
        uv pip install -e .
    else
        pip install -e .
    fi
fi

echo "✅ Starting Streamlit app..."
echo "📱 The workbench will open in your browser at http://localhost:8501"
echo ""

# Run streamlit
streamlit run app.py
