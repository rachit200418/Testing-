# Voice Assistant QA Platform - Makefile
# One-command setup and common operations

.PHONY: help install install-dev install-real test test-api test-unit test-stt test-intent test-llm test-multiturn test-safety test-ui test-perf test-promptfoo test-visual lint format typecheck run run-dev clean logs reports gen-audio augment-noise validate-manifest reset-db

# Default target
help:
	@echo "Voice Assistant QA Platform - Available Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install core dependencies (mock adapters only)"
	@echo "  make install-dev      Install core + dev dependencies"
	@echo "  make install-real     Install with real adapter dependencies (STT/LLM/TTS)"
	@echo ""
	@echo "Development:"
	@echo "  make run              Run the FastAPI server (uvicorn)"
	@echo "  make run-dev          Run with auto-reload"
	@echo "  make lint             Run ruff linting"
	@echo "  make format           Run black formatting"
	@echo "  make typecheck        Run mypy type checking"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests (unit + API)"
	@echo "  make test-api         Run API tests only"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-stt         Run STT quality tests (WER/CER)"
	@echo "  make test-intent      Run intent/slot accuracy tests"
	@echo "  make test-llm         Run DeepEval LLM evaluation tests"
	@echo "  make test-multiturn   Run multi-turn conversation tests"
	@echo "  make test-safety      Run safety/guardrails tests"
	@echo "  make test-ui          Run Playwright UI tests (requires running server)"
	@echo "  make test-perf        Run Locust performance tests (requires running server)"
@echo "  make test-promptfoo   Run promptfoo prompt regression tests"
  @echo "  make test-visual      Run visual regression tests"
  @echo ""
	@echo "Data & Reports:"
	@echo "  make logs             View recent logs"
	@echo "  make reports          List generated reports"
	@echo "  make gen-audio        Generate audio clips from manifest"
	@echo "  make augment-noise    Add noise to audio clips"
	@echo "  make validate-manifest Validate manifest CSV"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            Remove cache, logs, temp files"
	@echo "  make reset-db         Reset SQLite database"

# Installation
install:
	uv sync --no-dev

install-dev:
	uv sync

install-real:
	uv sync --extra real-stt --extra real-llm --extra real-tts

# Development
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

run-dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Code Quality
lint:
	uv run ruff check .

format:
	uv run black .

typecheck:
	uv run mypy app/

# Testing
test: test-unit test-api

test-unit:
	uv run pytest tests/ -v --tb=short -m "not api" -x

test-api:
	uv run pytest tests/api/ -v --tb=short

test-stt:
	uv run pytest tests/stt/ -v --tb=short

test-intent:
	uv run pytest tests/intent/ -v --tb=short

test-llm:
	uv run pytest tests/llm_eval/ -v --tb=short

test-multiturn:
	uv run pytest tests/multiturn/ -v --tb=short

test-safety:
	uv run pytest tests/safety/ -v --tb=short

test-ui:
	@echo "Starting server for UI tests..."
	@uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 & \
	SERVER_PID=$$!; \
	sleep 3; \
	uv run pytest tests/ui/ -v --tb=short; \
	kill $$SERVER_PID

test-perf:
	@echo "Starting server for performance tests..."
	@uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 & \
	SERVER_PID=$$!; \
	sleep 3; \
	uv run locust -f tests/perf/locustfile.py --headless -u 10 -r 2 -t 30s --host http://localhost:8000; \
	kill $$SERVER_PID

test-promptfoo:
	cd promptfoo && npx promptfoo eval -c promptfooconfig.yaml

test-visual:
	@echo "Starting server for visual tests..."
	@uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 & \
	SERVER_PID=$$!; \
	sleep 3; \
	uv run pytest tests/ui/test_visual.py -v --tb=short; \
	kill $$SERVER_PID

# Data & Logs
logs:
	tail -f logs/app.log 2>/dev/null || echo "No log file found. Run the server first."

reports:
	ls -la reports/ 2>/dev/null || echo "No reports directory yet."

gen-audio:
	uv run python tools/generate_audio.py --manifest data/manifest.csv --output-dir data/audio

augment-noise:
	uv run python tools/augment_noise.py --manifest data/manifest.csv --input-dir data/audio --output-dir data/audio

validate-manifest:
	uv run python tools/validate_manifest.py --manifest data/manifest.csv --audio-dir data/audio --stats

# Maintenance
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf logs/*.log 2>/dev/null || true
	rm -rf data/audio/uploads/* 2>/dev/null || true
	rm -rf data/audio/replies/* 2>/dev/null || true
	rm -rf .coverage 2>/dev/null || true
	rm -rf htmlcov 2>/dev/null || true

reset-db:
	rm -f data/app.db
	mkdir -p data
	uv run python -c "import asyncio; from app.tools.database import init_db; asyncio.run(init_db())"
	@echo "Database reset complete"