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

## 2026-10-05 — M8: E2E test + operator README
**Outcome:** Created `tests/e2e/test_full.py` (C22) — the complete "Done" gate from `vision.md` in a single monolithic test function exercising all 6 criteria against real Bedrock: (1) two tenants (tenant-a, tenant-b) each with a user, (2) each creates two conversations and exchanges multiple messages (5 send_and_verify_stream calls total), (3) every streamed reply asserted incremental (>1 text_delta before done), (4) backend restart survival (app1 shutdown → app2 with same DB → messages persisted, conversation lists intact, pi reloads session via --session and gives context-aware reply referencing "1 through 20"), (5) exhaustive cross-tenant rejection on all 5 per-ID endpoints both directions (10 conversation IDs × 5 endpoints = 20 opaque 404 checks, plus list isolation), (6) no-tools assertion (agent_end system message sections.tools contains "(none)"). Created `README.md` with prerequisites, setup, make targets, architecture overview, auth-seam replacement guide, and agent-tools extension point. Final validation pass: `make e2e` → 1 passed in 13.83s. `uv run pytest -q` → 37 passed in 51.12s. `uv run ruff check .` → All checks passed. `npm run build` → clean typecheck + bundled. `npm run lint` → clean. `npm run test` → 4 passed.
**Would do differently:** Nothing — clean pass on all validations.
**Blockers:** None.

## 2026-10-05 — M7: Cross-tenant isolation + no-tools assertion
**Outcome:** Added 5 IT-7 tests to `test_conversations.py` covering every endpoint that accepts a conversation/message ID with wrong-tenant headers: `GET /api/conversations/{id}` (opaque body, no title leak), `PATCH /api/conversations/{id}` (opaque 404), `DELETE /api/conversations/{id}` (opaque 404, original still exists), `GET /api/conversations/{id}/messages` (opaque 404), `POST /api/conversations/{id}/messages` (opaque 404, new for M7). All verify `_assert_opaque_404`: status 404, body contains only `detail` key, no leaked fields (tenant_id, user_id, title, content, pi_session_path). The `GET /api/conversations` list-isolation was already covered by IT-2 (returns empty array for wrong tenant — no data to leak). IT-10 (no-tools assertion) confirmed passing from M3: `uv run pytest -q -k "it10 or no_tools"` → 1 passed. Validation: `uv run ruff check .` → All checks passed. `uv run pytest -q` → 36 passed in 36.25s.
**Would do differently:** Nothing — clean pass.
**Blockers:** None.

## 2026-10-05 — M6: Frontend chat UI
**Outcome:** Created all six frontend components conforming to `design.md` tokens: `api.ts` (typed fetch wrappers for all 7 endpoints), `hooks/useStream.ts` (SSE hook using fetch + ReadableStream, accumulates text deltas, exposes state idle/streaming/error, AbortController support, fires onDone callback), `components/ConversationList.tsx` (sidebar 280px fixed, new/rename/delete with inline editing, active state with indigo-50 bg + left border, sorted by updated_at desc, truncated titles), `components/MessageThread.tsx` (user bubbles right-aligned indigo-50, assistant bubbles left-aligned white with border, ReactMarkdown for assistant content, auto-scroll via ref, empty state "Send a message to start", error bubble red), `components/MessageInput.tsx` (auto-growing textarea max 200px, Enter sends / Shift+Enter newline, send button with arrow icon, stop button with square icon during streaming, disabled states), `App.tsx` (two-column layout, state management for conversations/messages/active selection, optimistic user message append, stream integration). Unit test `useStream.test.ts` (IT-11): 4 tests — delta accumulation + onDone callback, error event handling, HTTP error response, abort graceful handling. Validation: `npm run build` → clean typecheck + bundled in 10.03s. `npm run lint` (tsc --noEmit) → clean. `npm run test` → 4 passed in 1.09s. **Browser manual check not performed** — this environment does not have a browser; the dev server manual check (conversations list, send message, streaming reply, switch conversations) cannot be verified here. TypeScript compilation and the useStream unit test provide code-level confidence but do not substitute for visual/functional testing.
**Would do differently:** Nothing significant — clean pass on all three automated validations.
**Blockers:** None.

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
