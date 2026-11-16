# Bridge Loan Platform. Sample data only.
# Python 3.12 is required. Override with: make setup PY=/path/to/python3.12
PY ?= python3.12
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup test lint dev demo smoke fixtures openapi

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"
	cd frontend && npm install

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check .
	cd frontend && npm run typecheck

dev:
	@trap 'kill 0' INT TERM EXIT; \
	$(BIN)/uvicorn bridge.api.app:create_app --factory --app-dir backend --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

demo:
	$(BIN)/python scripts/run_deal.py data/deals/bronx_mf data/deals/queens_mixed_use data/deals/overleveraged_bk --fresh --quiet

smoke:
	$(BIN)/python scripts/smoke.py

fixtures:
	$(BIN)/python scripts/generate_sample_deals.py
	$(BIN)/python scripts/generate_cached_fixtures.py

openapi:
	$(BIN)/python scripts/export_openapi.py
