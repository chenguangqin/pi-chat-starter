# Progress

## Patterns

### uv must be installed manually on this host
The host does not have `uv` pre-installed. Run `curl -LsSf https://astral.sh/uv/install.sh | sh` and add `~/.local/bin` to PATH before any `uv` command. Python 3.11 is at `/usr/bin/python3.11`.

### Hatchling needs explicit package config for flat-layout backends
When `pyproject.toml` uses hatchling and the source files are at the package root (not in a `src/` subdir), hatchling cannot auto-detect the wheel contents. Add `[tool.hatch.build.targets.wheel] packages = ["."]` to avoid the build error.

### Use Annotated for FastAPI Depends to satisfy ruff B008
Ruff's B008 rule flags `Depends(get_identity)` in function argument defaults. The fix is to use `Annotated[Identity, Depends(get_identity)]` as a type alias — this is the modern FastAPI pattern and avoids the lint error without suppressing the rule.

### SQLAlchemy ORM objects must use normal constructor, not __new__
Using `Conversation.__new__(Conversation)` then setting attributes bypasses SQLAlchemy's instrumentation setup and fails with `'Conversation' object has no attribute '_sa_instance_state'`. Always use the normal `Conversation(id=..., ...)` constructor, even for detached test fixtures.

### Short LLM prompts may produce only a single text_delta chunk
When testing for multi-chunk streaming (assert len(text_deltas) > 1), short prompts like "Reply with exactly three words" can arrive in one chunk from Bedrock. Use prompts that generate longer output ("List the numbers 1 through 20, each on its own line") to reliably produce multiple text_delta events.

### Pi get_state response includes sessionFile as full path
`get_state` response `data` includes: `sessionFile` (full path to the .jsonl session), `isStreaming`, `sessionId`, `model`, `thinkingLevel`, `messageCount`. No tools info is available in get_state — check the system message's `sections.tools` field in `agent_end` for the `(none)` assertion.

## 2026-10-05 — M5: Message history + restart survival
**Outcome:** Verified that `GET /api/conversations/{id}/messages` already exists from M2 (`routes/conversations.py:87`) — tenant-scoped via MessageRepository. Verified that ProcessManager.get_or_create already handles re-spawning dead processes with `--session <path>` (`process_manager.py:82-83`): when `conversation.pi_session_path` is set and the existing process is dead, `_reap_expired()` cleans it up and a new process is spawned with the saved session path. Added IT-5 test (send message with distinctive info "PINEAPPLE-42", shutdown pi process, send follow-up question — pi reloads session via --session and reply contains "pineapple") and IT-6 test (send message with "TURQUOISE", fully destroy app1 via lifespan exit, create app2 with same DB, verify GET messages returns 2 persisted messages, send follow-up — pi reloads session and reply contains "turquoise"). Validation: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 31 passed in 36.73s.
**Would do differently:** Nothing — the re-spawn infrastructure from M3 was already correct; M5 only needed the proof tests.
**Blockers:** None.

## 2026-10-05 — M4: Message send + streaming endpoint
**Outcome:** Created `sse.py` (SSE formatter: text_delta, status, error, done event types), `routes/messages.py` (POST /api/conversations/{id}/messages — saves user message, gets/creates pi process, checks is_streaming 409, sends prompt, returns StreamingResponse with SSE, saves assistant message on message_end, yields done_event on agent_settled, fire-and-forget abort via asyncio.create_task on disconnect), wired messages_router into `app.py`. Tests: `test_messages.py` with IT-4 (send message, verify >1 text_delta, done event, both messages persisted in DB), IT-8 (abort on disconnect — verify pi not stuck, can handle subsequent messages), plus edge cases (404 nonexistent conversation, 422 empty content, 401 no auth). Initial prompt "Reply with exactly three words" produced only 1 text_delta — fixed by using "List the numbers 1 through 20, each on its own line" which generates enough output for multi-chunk streaming. Same fix applied to IT-3 in test_pi_process.py. Validation: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 29 passed in 24.26s.
**Would do differently:** Use longer prompts from the start for tests that assert multi-chunk streaming — short model responses may arrive in a single chunk.
**Blockers:** None.

## 2026-10-05 — M3: Pi process lifecycle
**Outcome:** Created `pi_process.py` (PiProcess class: async subprocess, JSONL framing split on `b"\n"`, named methods send_prompt/send_get_state/abort/shutdown, state tracking starting→ready→streaming→idle→dead, stdout reader coroutine with per-line error handling, is_streaming flag, idle_since tracking) and `process_manager.py` (ProcessManager: conversation_id→PiProcess map, get_or_create with correct pi flags, cwd under DATA_DIR/tenants/<tid>/workdirs/<cid>/, MAX_PI_PROCESSES cap with CapacityError, idle timeout cleanup task, shutdown_all, pi version check on startup, session path saved from get_state to DB). Wired ProcessManager into app.py lifespan. Tests: IT-3 (spawn, get_state, send prompt, collect events through agent_settled, >1 text_delta verified), IT-10 (system message tools section contains "(none)"), cap→503 (max_pi_processes=1, second spawn raises CapacityError), workdir created under tenant data root, session path saved to Conversation object. Validation: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 24 passed in 12.30s.
**Would do differently:** Use the normal SQLAlchemy constructor from the start for test fixtures, not `__new__`.
**Blockers:** None.

## 2026-10-05 — M2: Identity stub + conversation CRUD with tenant isolation
**Outcome:** Created `auth.py` (IdentityMiddleware + Identity dataclass + get_identity helper), `repositories.py` (ConversationRepository with list/create/get_by_id/rename/delete, MessageRepository with list_for_conversation/create — every query scoped by tenant_id), `routes/conversations.py` (all 6 endpoints wired via APIRouter), updated `app.py` to wire middleware + router. Tests: `test_auth.py` (6 tests — IT-1: missing/empty headers → 401, valid → 200, health exempt) and `test_conversations.py` (13 tests — IT-2: full CRUD + cross-tenant isolation on get/rename/delete/messages all return 404). Validation: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 19 passed.
**Would do differently:** Nothing — clean pass.
**Blockers:** None.

## 2026-10-05 — M1: Project scaffold + database
**Outcome:** All scaffold files created. Backend: `pyproject.toml`, `config.py`, `database.py`, `models.py`, `app.py` with lifespan, Alembic migration `001_initial.py`. Frontend: `package.json`, Vite + React 18 + TypeScript + Tailwind, proxy config. Makefile with `dev`/`test`/`e2e` targets. Validation results: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 1 passed. `npm run build` → built in 9.27s, clean. `make dev` → both servers start, health endpoint returns `{"status":"ok"}`, frontend serves HTML.
**Would do differently:** Nothing — clean pass.
**Blockers:** None.
