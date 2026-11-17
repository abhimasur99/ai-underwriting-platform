# Bridge Loan Platform. Sample data only.
# Python 3.12 is required. Override with: make setup PY=/path/to/python3.12
PY ?= python3.12
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup test lint dev dev-retry dev-live demo smoke fixtures openapi

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

# BRIDGE_STEP_DELAY (seconds, 0 = off) makes each agent visibly "work" so the Flow tab is watchable.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	BRIDGE_STEP_DELAY=$${BRIDGE_STEP_DELAY:-1} $(BIN)/uvicorn bridge.api.app:create_app --factory --app-dir backend --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

# Same as dev, but Claude writes the narrative and words the chat (needs ANTHROPIC_API_KEY in .env).
dev-live:
	@BRIDGE_MODE=live $(MAKE) dev

# Same as dev, but the checker is made to disagree twice: shows the retry loop and escalation.
dev-retry:
	@BRIDGE_FORCE_MISMATCH=persist $(MAKE) dev

# Every sample deal that runs straight to a call (ridgewood_missing_arv stops at needs input; upload
# its followup/deal_summary.pdf in the UI to see it continue).
DEMO_DEALS := $(addprefix data/deals/,bronx_mf queens_mixed_use overleveraged_bk statenisland_mf harlem_mixed_use bronx_mf_64 yonkers_leaseup astoria_richarv washheights_gap mountvernon_exit)

demo:
	$(BIN)/python scripts/run_deal.py $(DEMO_DEALS) --fresh --quiet

smoke:
	$(BIN)/python scripts/smoke.py

fixtures:
	$(BIN)/python scripts/generate_sample_deals.py
	$(BIN)/python scripts/generate_cached_fixtures.py

openapi:
	$(BIN)/python scripts/export_openapi.py
	cd frontend && npm run gen:api
