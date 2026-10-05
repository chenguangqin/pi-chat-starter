# Progress

## Patterns

### uv must be installed manually on this host
The host does not have `uv` pre-installed. Run `curl -LsSf https://astral.sh/uv/install.sh | sh` and add `~/.local/bin` to PATH before any `uv` command. Python 3.11 is at `/usr/bin/python3.11`.

### Hatchling needs explicit package config for flat-layout backends
When `pyproject.toml` uses hatchling and the source files are at the package root (not in a `src/` subdir), hatchling cannot auto-detect the wheel contents. Add `[tool.hatch.build.targets.wheel] packages = ["."]` to avoid the build error.

## 2026-10-05 — M1: Project scaffold + database
**Outcome:** All scaffold files created. Backend: `pyproject.toml`, `config.py`, `database.py`, `models.py`, `app.py` with lifespan, Alembic migration `001_initial.py`. Frontend: `package.json`, Vite + React 18 + TypeScript + Tailwind, proxy config. Makefile with `dev`/`test`/`e2e` targets. Validation results: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 1 passed. `npm run build` → built in 9.27s, clean. `make dev` → both servers start, health endpoint returns `{"status":"ok"}`, frontend serves HTML.
**Would do differently:** Nothing — clean pass.
**Blockers:** None.
