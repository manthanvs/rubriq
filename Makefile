# RubriQ task runner.
#
# `make` is not installed on the Windows development machine — use the
# PowerShell mirror instead, which has the same target names:
#
#     .\make.ps1 test
#
# Both files must be kept in step. The Makefile is the portable one and the
# one the report quotes.

PY ?= python
PIP := $(PY) -m pip

.PHONY: help install run test lint fmt migrate revision seed-faculty seed

help:
	@echo "install   - install requirements.txt"
	@echo "run       - start the Streamlit app"
	@echo "test      - run pytest"
	@echo "lint      - ruff check"
	@echo "fmt       - ruff format + fix imports"
	@echo "migrate   - alembic upgrade head"
	@echo "revision  - alembic autogenerate, M=\"message\""
	@echo "seed-faculty - seed the faculty allow-list into users"
	@echo "seed      - demo dataset (arrives in Phase 7)"

install:
	$(PIP) install -r requirements.txt

run:
	$(PY) -m streamlit run app/main.py

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check core app tests alembic scripts

fmt:
	$(PY) -m ruff check --fix core app tests alembic scripts
	$(PY) -m ruff format core app tests alembic scripts

migrate:
	$(PY) -m alembic upgrade head

revision:
	@if [ -z "$(M)" ]; then echo 'Usage: make revision M="what changed"'; exit 1; fi
	$(PY) -m alembic revision --autogenerate -m "$(M)"

seed-faculty:
	$(PY) scripts/seed_faculty.py

seed:
	@echo "scripts/seed_demo.py arrives in Phase 7 (see CLAUDE.md §10)."
