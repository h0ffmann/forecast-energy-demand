# forecast-energy-demand — task runner
# Install: https://github.com/casey/just
# Usage:   just <recipe>

# Show available recipes
default:
    @just --list

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

# Install all dependencies and create .venv
install:
    uv sync

# Install including dev dependencies (jupyter, matplotlib, ruff, pyright)
install-dev:
    uv sync --all-extras

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

# Download all PJM regions (GitHub mirror, no auth)
download:
    uv run download_pjm.py --strategy direct

# Download specific regions only
download-regions regions="COMED DAYTON PJME EKPC FE NI":
    uv run download_pjm.py --strategy direct --regions {{regions}}

# Download via Kaggle API (requires KAGGLE_USERNAME + KAGGLE_KEY env vars)
download-kaggle:
    uv run download_pjm.py --strategy kaggle

# List available PJM regions
list-regions:
    uv run download_pjm.py --list-regions

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# Run baseline (SeasonalNaive) with downloaded data
baseline:
    uv run baseline.py --data data/raw

# Run baseline with synthetic data (no download needed)
baseline-synthetic:
    uv run baseline.py

# Run baseline on specific regions
baseline-regions regions="COMED DAYTON PJME":
    uv run baseline.py --data data/raw --regions {{regions}}

# ---------------------------------------------------------------------------
# MLflow
# ---------------------------------------------------------------------------

# Start MLflow tracking server
mlflow-server:
    uv run mlflow server --host 0.0.0.0 --port 5000

# Open MLflow UI in browser (assumes server is already running)
mlflow-open:
    xdg-open http://localhost:5000 || open http://localhost:5000

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

# Lint all Python files
lint:
    uv run ruff check .

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix .

# Type-check with pyright
typecheck:
    uv run pyright .

# Run lint + typecheck
check: lint typecheck

# ---------------------------------------------------------------------------
# AI context
# ---------------------------------------------------------------------------

# Pack repo into a single file for AI context
repomix:
    uv run repomix --ignore "data/,mlruns/,mlartifacts/,results/,.venv/,**/__pycache__"

# Pack and copy to clipboard (xclip on Linux, pbcopy on Mac)
repomix-clip:
    uv run repomix --ignore "data/,mlruns/,mlartifacts/,results/,.venv/,**/__pycache__" && cat repomix-output.xml | xclip -selection clipboard 2>/dev/null || cat repomix-output.xml | pbcopy 2>/dev/null || echo "Copy repomix-output.xml manually"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

# Remove generated results (keeps raw data)
clean-results:
    rm -rf results/ mlruns/ mlartifacts/

# Remove downloaded data (forces re-download)
clean-data:
    rm -rf data/

# Remove virtual environment (forces uv sync to recreate)
clean-venv:
    rm -rf .venv/

# Remove everything generated (data + results + venv)
clean: clean-results clean-data clean-venv