#!/usr/bin/env bash
# Arcane Redux Dashboard — Linux/macOS launcher
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo " ============================================================"
echo "  Arcane Redux Dashboard  |  AI YouTube Channel Operator"
echo "  http://localhost:7842"
echo " ============================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install Python 3.10+ from https://python.org"
    exit 1
fi

# Create virtual environment if missing
if [ ! -f ".venv/bin/python" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install dependencies
echo "[SETUP] Checking Python dependencies..."
pip install -r requirements.txt -q --disable-pip-version-check

# Create agent/.env from template if missing
if [ ! -f "agent/.env" ] && [ -f ".env.template" ]; then
    echo "[SETUP] Creating agent/.env from .env.template..."
    cp .env.template agent/.env
    echo "[SETUP] IMPORTANT: Edit agent/.env and fill in your API keys!"
fi

# Create output directories
mkdir -p agent/output/audio
mkdir -p agent/output/videos
mkdir -p agent/output/thumbnails
mkdir -p agent/output/scripts
mkdir -p agent/assets/avatar

echo ""
echo "[START] Launching dashboard..."
echo "[START] Browser will open automatically at http://localhost:7842"
echo "[START] Press Ctrl+C to stop the server"
echo ""

python app.py
