# Common commands. `make` alone lists them.
# Python is taken from the project venv; override with e.g. `make test PY=python3`.

PY ?= .venv/bin/python
QUESTIONS ?= eval/smoke_questions.txt

.DEFAULT_GOAL := help
.PHONY: help install db-up db-down ingest check run batch ui test lint ui-test requirements check-gold eval-retrieval

help: ## List the commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-14s %s\n", $$1, $$2}'

install: ## Create .venv if needed, install the package with its dev and UI extras
	test -d .venv || python3 -m venv .venv
	$(PY) -m pip install -e ".[dev,ui]"

db-up: ## Start Postgres + pgvector (docker-compose.yml)
	docker compose up -d

db-down: ## Stop the database container (the data volume is kept)
	docker compose down

ingest: ## Index data/corpus into the database (local, no LLM call)
	$(PY) -m claimverify.indexing.ingest --corpus_dir data/corpus

check: ## Show the passages the drafter retrieves for Q="..." (no LLM call)
	$(if $(Q),,$(error Q is required: make check Q="your question"))
	$(PY) -m claimverify.answering.query_check --query "$(Q)" --per_document

run: ## Answer and verify Q="..." (calls the LLM APIs, about 50K tokens)
	$(if $(Q),,$(error Q is required: make run Q="your question"))
	$(PY) -m claimverify.answering.pipeline --query "$(Q)"

batch: ## Answer and verify every question of QUESTIONS=file (calls the LLM APIs)
	$(PY) -m claimverify.answering.pipeline --questions_file $(QUESTIONS)

ui: ## Build the web UI and serve it on http://127.0.0.1:8000 (replay only; LIVE=1 allows live runs)
	cd ui && npm install --no-audit --no-fund && npm run build
	$(PY) -m claimverify.api.server $(if $(LIVE),,--no-live)

test: lint ## Lint, then the Python tests (no network, API key, GPU or database)
	$(PY) -m pytest -q

lint: ## Check the Python code with ruff
	$(PY) -m ruff check src tests scripts

ui-test: ## Type-check and test the web UI
	cd ui && npx tsc -b && npx vitest run

check-gold: ## Check the gold set: labels, sources, and that every quote is in the corpus (no LLM call)
	$(PY) -m claimverify.evaluation check-gold

eval-retrieval: ## Does the search bring back each proof? Methods and chunk sizes compared in memory (no LLM call)
	$(PY) -m claimverify.evaluation retrieval --methods dense bm25 hybrid rerank --chunk-sizes 256 510

requirements: ## Regenerate requirements.txt from pyproject.toml and the installed packages
	$(PY) scripts/freeze_requirements.py > requirements.txt
