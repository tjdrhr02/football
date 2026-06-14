VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install validate test init pipeline ingest aggregate analysis

install:
	$(PYTHON) -m pip install -e ".[dev]"

validate:
	$(PYTHON) scripts/validate_erd.py

test:
	$(VENV)/bin/pytest

init:
	$(PYTHON) -m football.cli.init_db

pipeline:
	$(PYTHON) run_pipeline.py --competition-id 43 --season-id 106

ingest:
	$(PYTHON) -m football.cli.ingest --table all

aggregate:
	$(PYTHON) -m football.cli.aggregate --table all

analysis:
	$(PYTHON) -m football.cli.analysis
