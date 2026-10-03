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

.PHONY: help install run test test-report lint fmt migrate revision seed-faculty seed reseed synopsis report

help:
	@echo "install   - install requirements.txt"
	@echo "run       - start the Streamlit app"
	@echo "test      - run pytest"
	@echo "test-report - write docs/test-report.txt, an SDLC artifact"
	@echo "lint      - ruff check"
	@echo "fmt       - ruff format + fix imports"
	@echo "migrate   - alembic upgrade head"
	@echo "revision  - alembic autogenerate, M=\"message\""
	@echo "seed-faculty - seed the faculty allow-list into users"
	@echo "seed      - build the demo dataset"
	@echo "reseed    - wipe and rebuild the demo dataset"
	@echo "synopsis  - build docs/report/RubriQ_Synopsis.docx"
	@echo "report    - build docs/report/RubriQ_Report.docx"

install:
	$(PIP) install -r requirements.txt

run:
	$(PY) -m streamlit run streamlit_app.py

test:
	$(PY) -m pytest

# The verbose run is checked in, because "the tests pass" is a claim and
# docs/test-report.txt is the evidence for it.
test-report:
	$(PY) -m pytest -o addopts="--strict-markers" -v --tb=short > docs/test-report.txt

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
	$(PY) scripts/seed_demo.py

reseed:
	$(PY) scripts/seed_demo.py --reset

# The .docx is generated, never hand-edited: docs/synopsis.md is the source.
synopsis:
	$(PY) scripts/build_synopsis_docx.py

# Assembled from docs/; the .docx is generated, never hand-edited.
report:
	$(PY) -m scripts.build_report_docx
