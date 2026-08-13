# Trader-IA — simulation-only quantitative research and paper-trading platform.
#
# Two entry points matter:
#   make demo     start it and open http://127.0.0.1:8000
#   make verify   run everything and print PASS / FAIL / WARN per area
#
# `make help` lists the rest.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY      := .venv/bin/python
PIP     := uv pip
PYTEST  := $(PY) -m pytest
RUFF    := .venv/bin/ruff
HOST    ?= 127.0.0.1
PORT    ?= 8000
export PYTHONPATH := packages/tia/src

.PHONY: help
help: ## Show this help
	@echo "Trader-IA — simulation only. No real money, no broker, no custody."
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------- setup

.PHONY: install
install: ## Create the venv and install everything (Python + frontend)
	@test -d .venv || python3 -m venv .venv
	@$(PIP) install -e ".[api,db,redis,llm,dev]" || .venv/bin/pip install -e ".[api,db,redis,llm,dev]"
	@cd frontend && npm install --no-fund --no-audit
	@$(MAKE) --no-print-directory build-frontend
	@echo "Installed. Run 'make diagnose' to confirm, then 'make demo'."

.PHONY: build-frontend
build-frontend: ## Build the dashboard into frontend/dist
	@cd frontend && npm run build

.PHONY: fixtures
fixtures: ## Regenerate the committed market fixtures (idempotent)
	@$(PY) scripts/generate_fixtures.py

.PHONY: diagnose
diagnose: ## Report what is installed, running and missing
	@./scripts/diagnose.sh

# --------------------------------------------------------------------- run

.PHONY: demo
demo: ## Start the API and the dashboard on http://$(HOST):$(PORT)
	@mkdir -p data/runtime
	@echo "Trader-IA on http://$(HOST):$(PORT) — simulated capital only."
	@echo "Credentials: TIA_DEMO_USER / TIA_DEMO_PASSWORD, or a generated one printed below."
	@$(PY) -m uvicorn tia.api.main:app --host $(HOST) --port $(PORT)

.PHONY: dev
dev: ## Frontend dev server on :3000 proxying to the API on :8000
	@cd frontend && npm run dev

.PHONY: backtest
backtest: ## Run one backtest against the fixtures and print the evidence statement
	@$(PY) scripts/run_backtest.py

# --------------------------------------------------------------------- checks

.PHONY: lint
lint: ## ruff over the package, tests and scripts
	@$(RUFF) check packages tests scripts

.PHONY: typecheck
typecheck: ## TypeScript type check for the dashboard
	@cd frontend && npm run typecheck

.PHONY: test
test: ## Unit and property tests (fast)
	@$(PYTEST) tests/unit tests/property -q

.PHONY: test-failure
test-failure: ## Failure-injection tests (outages, corruption, divergence, restart)
	@$(PYTEST) tests/failure -q

.PHONY: test-e2e
test-e2e: ## End-to-end pipeline tests (slow — starts real runtimes)
	@$(PYTEST) tests/e2e -q

.PHONY: test-all
test-all: ## Every Python test
	@$(PYTEST) tests -q

.PHONY: smoke
smoke: ## Start the server, drive the dashboard in a browser, stop it
	@./scripts/smoke.sh

.PHONY: verify
verify: ## Everything: lint, types, tests, e2e, smoke — with a PASS/FAIL summary
	@./scripts/verify.sh

# --------------------------------------------------------------------- clean

.PHONY: clean
clean: ## Remove build artefacts and the runtime database
	@rm -rf .pytest_cache .ruff_cache .hypothesis dist build
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -f data/runtime/*.db data/runtime/*.db-wal data/runtime/*.db-shm
	@echo "Cleaned. Fixtures and source are untouched."

.PHONY: clean-all
clean-all: clean ## Also remove the venv and node_modules
	@rm -rf .venv frontend/node_modules frontend/dist
