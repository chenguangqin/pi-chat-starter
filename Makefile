BACKEND_DIR := src/backend
FRONTEND_DIR := src/frontend

.PHONY: dev dev-backend dev-frontend test test-backend test-frontend e2e lint install

install:
	cd $(BACKEND_DIR) && uv sync --all-extras
	cd $(FRONTEND_DIR) && npm install

dev-backend:
	cd $(BACKEND_DIR) && uv run uvicorn app:create_app --factory --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

dev:
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

test-backend:
	cd $(BACKEND_DIR) && uv run pytest -q

test-frontend:
	cd $(FRONTEND_DIR) && npm run test

test: test-backend test-frontend

lint:
	cd $(BACKEND_DIR) && uv run ruff check .
	cd $(FRONTEND_DIR) && npm run lint
	cd $(FRONTEND_DIR) && npm run typecheck

e2e:
	cd $(BACKEND_DIR) && uv run pytest tests/e2e/ -q
