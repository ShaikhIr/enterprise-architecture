# Common dev commands. Run from the backend/ directory.
#
# These are the same commands CI runs (.github/workflows/backend-ci.yml), so a
# green `make check` locally means a green pipeline.
#
# PYTHON defaults to whatever is on PATH; override it to skip activating a venv:
#   make check PYTHON=venv/Scripts/python.exe     (Windows)
#   make check PYTHON=venv/bin/python             (Linux/macOS)

PYTHON ?= python

.PHONY: help install lint lint-fix type test test-cov check migrate migration \
        downgrade drift seed run

help:  ## Show available targets
	@echo "Targets:"
	@echo "  install     Install the project with dev dependencies"
	@echo "  lint        Run ruff"
	@echo "  lint-fix    Run ruff with --fix"
	@echo "  type        Run mypy (strict)"
	@echo "  test        Run the test suite"
	@echo "  test-cov    Run the test suite with a coverage report"
	@echo "  check       lint + type + drift + test (what CI gates on)"
	@echo "  migrate     Apply migrations up to head"
	@echo "  migration   Generate a migration:  make migration m='describe it'"
	@echo "  downgrade   Roll back one migration"
	@echo "  drift       Fail if models and migrations disagree"
	@echo "  seed        Seed the admin user and RBAC permissions"
	@echo "  run         Start the dev server with reload"

install:  ## Install the project with dev dependencies
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

lint:  ## Run ruff
	$(PYTHON) -m ruff check src scripts tests

lint-fix:  ## Run ruff, applying safe fixes
	$(PYTHON) -m ruff check src scripts tests --fix

type:  ## Run mypy in strict mode
	$(PYTHON) -m mypy src tests scripts

test:  ## Run the test suite
	$(PYTHON) -m pytest

test-cov:  ## Run the test suite with a coverage report
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing

drift:  ## Fail if the ORM models have drifted from migration history
	$(PYTHON) -m alembic check

check: lint type drift test  ## Everything CI gates on

migrate:  ## Apply migrations up to head
	$(PYTHON) -m alembic upgrade head

migration:  ## Generate a migration: make migration m="create widgets table"
	@if [ -z "$(m)" ]; then echo "usage: make migration m=\"describe the change\""; exit 1; fi
	$(PYTHON) -m alembic revision --autogenerate -m "$(m)"

downgrade:  ## Roll back the most recent migration
	$(PYTHON) -m alembic downgrade -1

seed:  ## Seed the admin user and RBAC permissions
	$(PYTHON) -m scripts.seed_data
	$(PYTHON) -m scripts.seed_rbac

run:  ## Start the dev server with reload
	$(PYTHON) -m uvicorn src.main:app --reload --port 6769
