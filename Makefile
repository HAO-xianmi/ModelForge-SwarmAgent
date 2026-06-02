# ModelForge-Swarm developer tasks.
# On Windows, run targets via `make <target>` (Git Bash / WSL) or copy the
# command. Pure-Python targets also work from PowerShell.

.PHONY: help install install-science lint type test test-unit test-integration test-e2e \
        test-security demo doctor api web clean

help:
	@echo "Targets: install install-science lint type test demo doctor api web clean"

install:
	python -m pip install -e ".[dev]"

install-science:
	python -m pip install -e ".[science]"

lint:
	python -m ruff check src tests

type:
	python -m mypy

test:
	python -m pytest

test-unit:
	python -m pytest tests/unit

test-integration:
	python -m pytest -m integration

test-e2e:
	python -m pytest -m e2e

test-security:
	python -m pytest -m security

doctor:
	python -m modelforge.cli.main doctor

demo:
	python -m modelforge.cli.main demo

api:
	python -m uvicorn modelforge.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

clean:
	python -c "import shutil,glob,os; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache','.mypy_cache','.ruff_cache','htmlcov'] + glob.glob('**/__pycache__', recursive=True)]"
