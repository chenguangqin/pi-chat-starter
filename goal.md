# Goal — common_agent

## Goal

Build a web chat application with a Python backend (FastAPI) wrapping the **pi agent** as its LLM runtime. Users hold conversations over Bedrock-backed pi with streaming replies. Conversations persist across restarts. Tenant isolation is enforced at the data layer. Pi's built-in tools are fully disabled.

**"Done" = the e2e test from `vision.md` passes against a real Bedrock-backed pi.** Code existing is not done.

## Scope

**In:** chat web UI (conversation list, message thread, streaming, new/rename/delete), Python API, pi RPC integration, SQLite persistence, tenant isolation enforcement + tests, local start (`make dev`), e2e test (`make e2e`), operator README.

**Out:** real authentication, agent tools/RAG/file upload, cloud deployment/IaC/CI, billing/quotas/rate limiting, admin console, model picker UI, prompt templates, dark mode.

## Preconditions

| Milestone | Requires |
|---|---|
| M3 | `pi` 1.0.2 installed and Bedrock credentials available (ambient IAM role + `AWS_PROFILE=default`) |
| M4 | M2 (conversation CRUD) and M3 (pi process management) both complete |
| M5 | M4 (message endpoint) complete |
| M6 | M2 (API exists to call) and M4 (streaming endpoint exists) complete |
| M7 | M2, M4, M5 complete (all endpoints exist to test) |
| M8 | All prior milestones complete |

## Milestones

- [x] **M1: Project scaffold + database**
  - Initialize backend: `pyproject.toml` (FastAPI, SQLAlchemy, uvicorn, alembic, httpx, pytest, pytest-asyncio, ruff), `alembic.ini`, initial migration creating `conversations` and `messages` tables
  - Initialize frontend: `package.json`, Vite + React 18 + TypeScript + Tailwind CSS, `vite.config.ts` with `/api` proxy to `localhost:8000`
  - Backend: `config.py` (env vars: `PI_MODEL`, `DATA_DIR`, `PI_IDLE_TIMEOUT_SECONDS`, `MAX_PI_PROCESSES` default 20), `database.py` (async SQLAlchemy engine, WAL mode pragma, session factory), `models.py` (Conversation, Message ORM models), `app.py` (FastAPI factory with lifespan)
  - `Makefile` with `make dev` (starts backend + frontend)
  - **Validation:** `uv run ruff check .` clean, `uv run pytest -q` passes (empty/trivial test), `npm run build` succeeds, `make dev` starts both servers (manual check: frontend serves, backend responds to a health endpoint)

- [x] **M2: Identity stub + conversation CRUD with tenant isolation**
  - `auth.py`: middleware reads `X-Tenant-ID` and `X-User-ID` headers → `Identity` on request state. Missing/empty → 401.
  - `repositories.py`: `ConversationRepository` with `list`, `create`, `get_by_id`, `rename`, `delete` — every method requires `tenant_id`, every query has `WHERE tenant_id = :tid`. `MessageRepository` with `list_for_conversation`, `create` — joins through Conversation for tenant check.
  - `routes/conversations.py`: all 6 endpoints from the API surface in `architecture.md`
  - Tests: `test_auth.py` (IT-1: missing headers → 401, valid headers → identity set), `test_conversations.py` (IT-2: CRUD works, cross-tenant access → 404)
  - **Validation:** `uv run pytest -q` passes, `uv run ruff check .` clean

- [x] **M3: Pi process lifecycle**
  - `pi_process.py`: `PiProcess` class — async subprocess via `asyncio.create_subprocess_exec`, JSONL framing (split on `b"\n"` only), named methods only (`send_prompt`, `send_get_state`, `abort`, `shutdown`), state tracking (starting/ready/streaming/idle/dead), stdout reader coroutine with per-line error handling, `is_streaming` flag
  - `process_manager.py`: `ProcessManager` — maps `conversation_id → PiProcess`, `get_or_create(conversation)` that spawns with correct flags (`--mode rpc --no-tools --no-context-files --provider amazon-bedrock --model $PI_MODEL --session-dir <tenant_dir>`), saves `pi_session_path` from `get_state` to conversation record, re-spawns with `--session <saved_path>`, idle timeout cleanup task, `shutdown_all()`
  - `ProcessManager` spawns each process with **cwd `<DATA_DIR>/tenants/<tid>/workdirs/<cid>/`**, created on demand (idempotent) and removed when the conversation is deleted — NOT `/tmp` (see `architecture.md` → Reviewer Decisions)
  - `ProcessManager` enforces `MAX_PI_PROCESSES` (default 20): reap idle-timed-out processes first, then refuse with **HTTP 503** rather than spawning past the cap. No queuing, no eviction of a live process.
  - `AWS_PROFILE` must be set explicitly in the child environment (see `tech-env.md`) or pi will not expose the Bedrock provider
  - App factory wires ProcessManager into lifespan (create on startup, shutdown on teardown)
  - Pi version check on startup (`pi --version` must be `1.0.2`)
  - Tests: `test_pi_process.py` (IT-3: spawn pi, get_state, send prompt, receive events through agent_settled, verify >1 text_delta; IT-10: no tools enabled; plus: the cap yields 503, and the workdir is created under the tenant data root)
  - **Validation:** `uv run pytest -q` passes (tests hit real pi + real Bedrock), `uv run ruff check .` clean

- [ ] **M4: Message send + streaming endpoint**
  - `sse.py`: SSE formatter — transforms pi events to `data: {...}\n\n` lines (text_delta, status, error, done)
  - `routes/messages.py`: `POST /api/conversations/{id}/messages` — saves user message to DB first, calls `ProcessManager.get_or_create`, checks `is_streaming` (409 if busy), sends prompt to pi, returns `StreamingResponse` with SSE content type, saves assistant message on `message_end`, aborts pi on client disconnect
  - Tests: `test_messages.py` (IT-4: send message, verify SSE stream has >1 text_delta chunk before done, verify user + assistant messages in DB; IT-8: client disconnect triggers abort)
  - **Validation:** `uv run pytest -q` passes (hits real pi + Bedrock), `uv run ruff check .` clean

- [ ] **M5: Message history + restart survival**
  - `GET /api/conversations/{id}/messages` returns messages from DB, scoped by tenant
  - ProcessManager re-spawn path: when pi process is dead and conversation has `pi_session_path`, spawn with `--session <path>` to reload history
  - Tests: IT-5 (send messages, kill pi process, send again, verify context-aware reply), IT-6 (send messages, recreate app instance with same DB, verify messages listed, send new message, verify pi reloads session)
  - **Validation:** `uv run pytest -q` passes, `uv run ruff check .` clean

- [ ] **M6: Frontend chat UI**
  - `App.tsx`: two-column layout (sidebar 280px + main), conforming to `design.md` tokens
  - `api.ts`: typed fetch wrappers for all endpoints (list/create/get/rename/delete conversations, list messages, send message)
  - `useStream.ts`: SSE hook using `fetch` + `ReadableStream`, accumulates text deltas, exposes state (idle/streaming/error), handles done and error events, supports abort via `AbortController`
  - `ConversationList.tsx`: sidebar with conversation items, new/rename/delete, active state, sorted by updated_at desc
  - `MessageThread.tsx`: renders message history, streaming assistant text, error messages, auto-scroll to bottom, markdown rendering for assistant messages
  - `MessageInput.tsx`: auto-growing textarea, Enter to send / Shift+Enter for newline, disabled while streaming, stop button during streaming
  - Unit test: `useStream.test.ts` (IT-11: mock SSE, verify delta accumulation and error handling)
  - **Validation:** `npm run build` succeeds (clean typecheck), `npm run lint` clean, `npm run test` passes, dev server manual check (conversations list, send message, see streaming reply, switch conversations)

- [ ] **M7: Cross-tenant isolation + no-tools assertion**
  - Dedicated test `test_conversations.py` additions or new file: IT-7 — for EVERY endpoint that accepts a conversation or message id, attempt access with wrong tenant's identity headers → assert 404 and empty/opaque response body
  - IT-10 assertion (if not already covered in M3): verify pi process reports no enabled tools
  - **Validation:** `uv run pytest -q` passes, every endpoint covered by cross-tenant test

- [ ] **M8: E2E test + operator README**
  - `tests/e2e/test_full.py` (C22): the complete "Done" gate from `vision.md`:
    1. Creates two tenants (tenant-a, tenant-b), each with a user
    2. Each user creates two conversations and exchanges several messages with real Bedrock pi
    3. Asserts streamed replies arrived incrementally (>1 text_delta chunk before done)
    4. Asserts history survives a backend restart (recreate app, verify messages, send new message)
    5. Asserts every cross-tenant access attempt is refused (all endpoints, both directions)
    6. Asserts agent has no file or shell tools (get_state check)
  - `README.md`: operator docs — prerequisites (Python 3.11+, Node 22+, pi 1.0.2, AWS credentials), setup steps, `make dev`, `make test`, `make e2e`, where the auth seam is and how to replace it, where to add agent tools later
  - Final validation pass: `uv run ruff check .`, `uv run mypy .` (if mypy config established), `npm run build`, `npm run lint`, `npm run test`
  - **Validation:** `make e2e` passes against real Bedrock. All lint/type checks clean.

## Validation (end-to-end)

The ultimate gate is `make e2e` — a single command that runs the e2e test from M8. This test exercises every seam from the integration test list in `architecture.md` and maps 1:1 to the six "Done" criteria in `vision.md`.

## Status

M3 complete. Starting M4 next turn.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Default model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (via `PI_MODEL` env var) | Only verified model on this host. Cheap for a chat shell. Configurable. |
| D2 | Pi process idle timeout: 15 min default (via `PI_IDLE_TIMEOUT_SECONDS`) | Balances memory vs. latency. Configurable. |
| D3 | Identity stub via `X-Tenant-ID` / `X-User-ID` headers | Simplest replaceable stub. One file to swap for real auth. |
| D4 | POST returns SSE stream (not POST + separate GET) | Eliminates race between message creation and stream subscription. |
| D5 | Pi cwd: `<DATA_DIR>/tenants/<tid>/workdirs/<cid>/` (**reviewer override** of the earlier `/tmp/pi-<cid>`) | `/tmp` is cleaned by tmpfiles.d / reboots and the failure (pi starting in a vanished cwd) is obscure. Keeps all tenant state on one path prefix. `-nc` still disables context-file discovery. |
| D6 | Session reload via saved `pi_session_path` + `--session <path>` | Deterministic across re-spawns regardless of cwd. |
| D7 | PiProcess exposes only named methods, not generic send | Prevents accidental `bash` command construction. |
| D8 | 409 Conflict on concurrent prompt to same conversation | Simpler than pi's `streamingBehavior` queuing. Fail-fast for the user. |
| D9 | Conversations table uses TEXT PRIMARY KEY (UUID) | No auto-increment; UUIDs are generated in Python. Simpler for a multi-process system. |
| D10 | No auto-generated conversation titles in v1 (**reviewer decision**) | Default title `"New conversation"`; rename endpoint is the only path. Avoids a second LLM call. Pure increment, deferred. |
| D11 | `MAX_PI_PROCESSES` default 20, over-cap requests get HTTP 503 (**reviewer decision**) | Prevents linear memory growth into OOM. Reap idle-timed-out processes before refusing. No queuing, no eviction. |

## Open Questions

None blocking. All six questions from `vision.md` were resolved in `research.md` and committed in `architecture.md`.
