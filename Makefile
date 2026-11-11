PYTHON ?= python3
ifneq ($(wildcard .venv/bin/python),)
  PYTHON := .venv/bin/python
endif

export PYTHONPATH := .

.PHONY: setup ingest ingest-fixtures build test export app all lint pipeline pipeline-fixtures

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt

ingest:
	$(PYTHON) scripts/ingest.py

ingest-fixtures:
	$(PYTHON) scripts/ingest.py --source fixtures

build:
	$(PYTHON) scripts/build.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

export:
	$(PYTHON) scripts/export.py
	$(PYTHON) scripts/generate_brief.py

app:
	$(PYTHON) -m streamlit run app/Home.py --server.headless true

all: ingest build test export

pipeline:
	$(PYTHON) scripts/run_pipeline.py

pipeline-fixtures:
	$(PYTHON) scripts/run_pipeline.py --source fixtures

