.PHONY: install install-dev test lint format typecheck clean run-parser run-download help

# Default target
help:
	@echo "Ponderosa - Podcast Intelligence Pipeline"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install all dependencies (including dev)"
	@echo ""
	@echo "Development:"
	@echo "  make test          Run tests"
	@echo "  make lint          Run linter (ruff)"
	@echo "  make format        Format code (ruff)"
	@echo "  make typecheck     Run type checker (mypy)"
	@echo "  make check         Run all checks (lint, typecheck, test)"
	@echo ""
	@echo "CLI Commands:"
	@echo "  make run-parser    Parse Flirting with Models RSS feed"
	@echo "  make run-download  Download episodes locally"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove build artifacts and caches"

# Installation
install:
	uv sync

install-dev:
	uv sync --all-extras

# Testing
test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=src/ponderosa --cov-report=term-missing

# Code quality
lint:
	uv run ruff check src/ tests/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/

check: lint typecheck test

# CLI commands
run-parser:
	uv run ponderosa parse-feed "https://flirtingwithmodels.libsyn.com/rss" -n 5

run-download:
	uv run ponderosa download "https://flirtingwithmodels.libsyn.com/rss" -n 1 -o ./downloads

# Cleanup
clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf __pycache__
	rm -rf src/**/__pycache__
	rm -rf tests/__pycache__
	rm -rf dist
	rm -rf *.egg-info
	rm -rf downloads
	rm -rf .coverage
