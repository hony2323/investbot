# Dev convenience for the investbot monorepo.
# Requires `uv` (https://docs.astral.sh/uv/) and Node for the web app.

.PHONY: install test cli api web dev

# Install the Python workspace (core lib + API) into .venv.
install:
	uv sync
	cd apps/web && npm install

# Run the core test suite.
test:
	uv run pytest packages/core

# Run the FastAPI service (http://localhost:8000, docs at /docs).
api:
	uv run uvicorn investbot_api.main:app --reload --app-dir apps/api

# Run the Vite dev server (http://localhost:5173, proxies /api -> :8000).
web:
	cd apps/web && npm run dev

# Run API + web together (Ctrl-C stops both).
dev:
	$(MAKE) -j2 api web
