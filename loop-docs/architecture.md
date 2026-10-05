# Architecture — common_agent

## Component List

### Backend (Python / FastAPI)

| # | Component | File(s) | Purpose |
|---|---|---|---|
| C1 | **App factory** | `src/backend/app.py` | Creates FastAPI app, registers middleware/routes, manages lifespan (startup/shutdown) |
| C2 | **Config** | `src/backend/config.py` | Reads env vars (`PI_MODEL`, `DATA_DIR`, `PI_IDLE_TIMEOUT_SECONDS`), holds constants (expected pi version) |
| C3 | **Identity stub** | `src/backend/auth.py` | Middleware that reads `X-Tenant-ID` / `X-User-ID` headers → request-scoped `Identity`. THE seam for real auth. |
| C4 | **Database** | `src/backend/database.py` | SQLAlchemy 2.x async engine + session factory, WAL pragma, Alembic config |
| C5 | **ORM models** | `src/backend/models.py` | `Conversation` (id, tenant_id, user_id, title, pi_session_path, created_at, updated_at) and `Message` (id, conversation_id, role, content, created_at) |
| C6 | **ConversationRepository** | `src/backend/repositories.py` | All conversation CRUD. Every method requires `tenant_id` — this is the tenant-isolation enforcement layer. |
| C7 | **MessageRepository** | `src/backend/repositories.py` | All message read/write. Scoped through conversation ownership (join through Conversation.tenant_id). |
| C8 | **Conversation routes** | `src/backend/routes/conversations.py` | `GET /api/conversations`, `POST /api/conversations`, `GET /api/conversations/{id}`, `PATCH /api/conversations/{id}`, `DELETE /api/conversations/{id}`, `GET /api/conversations/{id}/messages` |
| C9 | **Message route** | `src/backend/routes/messages.py` | `POST /api/conversations/{id}/messages` — accepts user message, returns SSE stream of the assistant reply |
| C10 | **PiProcess** | `src/backend/pi_process.py` | Wraps one `asyncio.create_subprocess_exec` pi instance. JSONL framing (split on `b"\n"` only), command send, event async-iteration, state tracking (starting → ready → streaming → idle → dead). |
| C11 | **ProcessManager** | `src/backend/process_manager.py` | Maps conversation_id → PiProcess. `get_or_create(conversation)`, idle-timeout cleanup (background task), shutdown-all on app teardown. |
| C12 | **SSE formatter** | `src/backend/sse.py` | Transforms pi events into SSE `data:` lines. Handles text_delta, error, retry-status, and done event types. |
| C13 | **Alembic migrations** | `src/backend/alembic/` | Initial migration creates `conversations` and `messages` tables |

### Frontend (React / TypeScript / Vite / Tailwind)

| # | Component | File(s) | Purpose |
|---|---|---|---|
| C14 | **App shell** | `src/frontend/src/App.tsx` | Root layout: sidebar + main panel |
| C15 | **ConversationList** | `src/frontend/src/components/ConversationList.tsx` | Sidebar listing conversations, new/rename/delete actions |
| C16 | **MessageThread** | `src/frontend/src/components/MessageThread.tsx` | Renders message history, auto-scrolls, shows streaming text |
| C17 | **MessageInput** | `src/frontend/src/components/MessageInput.tsx` | Text area + send button, disabled while streaming |
| C18 | **useStream hook** | `src/frontend/src/hooks/useStream.ts` | SSE streaming via `fetch` + `ReadableStream`. Accumulates deltas, surfaces errors, exposes state (idle/streaming/error). |
| C19 | **API client** | `src/frontend/src/api.ts` | Typed fetch wrappers for all backend endpoints |

### Infrastructure

| # | Component | File(s) | Purpose |
|---|---|---|---|
| C20 | **Makefile** | `Makefile` | `make dev` (start both servers), `make test` (all tests), `make e2e` (end-to-end test) |
| C21 | **Backend tests** | `src/backend/tests/` | pytest unit + integration tests |
| C22 | **E2E test** | `src/backend/tests/e2e/test_full.py` | The "Done" gate from `vision.md` — two tenants, real Bedrock, streaming, restart, isolation, no-tools |

---

## Wiring / Dependency Topology

### Request flow diagram

```
Browser (C14–C19)
  │
  │ fetch / SSE (HTTP)
  ▼
Vite proxy (/api/* → localhost:8000)
  │
  ▼
FastAPI app (C1)
  │
  ├─ Identity Stub middleware (C3)
  │   reads X-Tenant-ID / X-User-ID → Identity on request state
  │
  ├─ Conversation Routes (C8)
  │   │
  │   └─ ConversationRepository (C6) ──► SQLite via SQLAlchemy (C4, C5)
  │       └─ every query: WHERE tenant_id = :tid
  │
  └─ Message Route (C9)
      │
      ├─[1] MessageRepository (C7) ──► SQLite  (save user message FIRST)
      │
      ├─[2] ProcessManager (C11)
      │      │
      │      └─ get_or_create(conversation)
      │           │
      │           └─ PiProcess (C10) spawn:
      │                pi --mode rpc --no-tools --no-context-files
      │                  --provider amazon-bedrock
      │                  --model $PI_MODEL
      │                  --session-dir <data>/tenants/<tid>/sessions
      │                  [--session <saved_path>]     ← on re-spawn
      │                  AWS_PROFILE=default
      │
      ├─[3] PiProcess.send_prompt(message)
      │      writes {"type":"prompt","id":"...","message":"..."}\n to stdin
      │
      ├─[4] PiProcess stdout reader (async coroutine)
      │      reads bytes, splits on b"\n", yields parsed JSON events
      │      ▼
      │   SSE Formatter (C12)
      │      transforms pi events → SSE data: lines
      │      ▼
      │   StreamingResponse → Client
      │
      ├─[5] on message_end → MessageRepository (C7) save assistant message
      │
      └─[6] on client disconnect → PiProcess.abort() → pi stdin {"type":"abort"}
                                    wait for agent_settled, then release
```

### Numbered interactions (every cross-component call)

| # | From | To | Interaction | Notes |
|---|---|---|---|---|
| W1 | Client (C19) | FastAPI (C1) | HTTP request | All API calls |
| W2 | FastAPI (C1) | Identity Stub (C3) | Middleware invocation | Runs on every `/api/*` request |
| W3 | Identity Stub (C3) | Route handlers (C8, C9) | Sets `request.state.identity` | `Identity(tenant_id, user_id)` |
| W4 | Conversation Routes (C8) | ConversationRepository (C6) | `list`, `create`, `get`, `rename`, `delete` | Always passes `tenant_id` |
| W5 | ConversationRepository (C6) | Database (C4) | SQLAlchemy async queries | `WHERE tenant_id = :tid` on every query |
| W6 | Message Route (C9) | MessageRepository (C7) | `save_user_message` | Before prompting pi |
| W7 | MessageRepository (C7) | Database (C4) | SQLAlchemy async queries | Joins through Conversation to enforce tenant_id |
| W8 | Message Route (C9) | ProcessManager (C11) | `get_or_create(conversation)` | Returns a ready PiProcess |
| W9 | ProcessManager (C11) | PiProcess (C10) | `spawn()` / return cached | Spawns pi subprocess if not alive |
| W10 | PiProcess (C10) | pi subprocess (external) | Write JSONL to stdin | `prompt`, `get_state`, `abort` commands |
| W11 | pi subprocess (external) | PiProcess (C10) | Read JSONL from stdout | Events: `agent_start`, `message_update`, `agent_settled`, etc. |
| W12 | PiProcess (C10) | SSE Formatter (C12) | Yields parsed events | Async iteration |
| W13 | SSE Formatter (C12) | Client (C18) | SSE `data:` frames over HTTP | `text/event-stream` response |
| W14 | Message Route (C9) | MessageRepository (C7) | `save_assistant_message` | On `message_end` or stream completion |
| W15 | Message Route (C9) | PiProcess (C10) | `abort()` | On client disconnect |
| W16 | ProcessManager (C11) | PiProcess (C10) | `shutdown()` | Idle timeout cleanup + app teardown |
| W17 | App factory (C1) | ProcessManager (C11) | Lifespan create/destroy | Startup: create. Shutdown: terminate all. |
| W18 | App factory (C1) | Database (C4) | Lifespan create/dispose | Startup: create engine + run migrations. Shutdown: dispose. |
| W19 | App factory (C1) | Config (C2) | Read on startup | Pi version check (`pi --version`), load settings |
| W20 | Conversation Routes (C8) | MessageRepository (C7) | `list_messages(conversation_id, tenant_id)` | For GET /conversations/{id}/messages |
| W21 | Frontend App (C14) | API client (C19) | Function calls | All data fetching |
| W22 | Frontend App (C14) | useStream (C18) | Hook invocation | SSE connection lifecycle |
| W23 | useStream (C18) | Message Route (C9) | `fetch` with streaming body read | POST that returns SSE |
| W24 | ConversationList (C15) | API client (C19) | CRUD calls | List, create, rename, delete |
| W25 | MessageThread (C16) | API client (C19) | `listMessages()` | Load history on conversation switch |

### Lifecycle flows

**First message in a new conversation:**
C19 → C1 → C3 → C9 → C7 (save user msg) → C11 (get_or_create) → C10 (spawn pi) → pi subprocess (get_state, verify ready) → C10 (send_prompt) → pi stdout → C10 (parse events) → C12 (format SSE) → C18 (client) + C7 (save assistant msg on completion)

**Subsequent message (process alive):**
C19 → C1 → C3 → C9 → C7 (save user msg) → C11 (return cached C10) → C10 (send_prompt) → pi stdout → C12 → C18 + C7

**Subsequent message (process died/timed out):**
C19 → C1 → C3 → C9 → C7 (save user msg) → C11 (get_or_create: process dead, re-spawn with `--session <saved_path>`) → C10 (spawn, reload session) → C10 (send_prompt) → …

---

## Critique

Challenges to the proposed design and whether each is a real gap:

### Critique 1: POST-returns-SSE breaks REST conventions

A `POST /api/conversations/{id}/messages` that returns `Content-Type: text/event-stream` is non-standard. Some HTTP clients / proxies may not handle it.

**Assessment:** For this local-only app behind a Vite dev proxy, no intermediate infrastructure interferes. The alternative — POST to create + GET to subscribe — introduces a race (the stream could start before the client subscribes). The simplicity gain outweighs the convention cost. **Not a gap.**

### Critique 2: Pi session file lookup on re-spawn depends on knowing the file path

Pi's session file paths include a timestamp prefix: `<session-dir>/--<cwd>--/<timestamp>_<session-id>.jsonl`. Using `--session-id` to re-find a session depends on the cwd matching. If the cwd changes between spawns, pi may create a new session instead.

**Assessment: This IS a real gap.** The proposed design must save the full `sessionFile` path (from `get_state` after first spawn) into the `Conversation.pi_session_path` column and re-spawn with `--session <saved_path>`. This makes re-spawn deterministic regardless of cwd. **Fixed in reconcile.**

### Critique 3: Two concurrent prompts to the same conversation

If two browser tabs (or a fast double-click) both POST a message to the same conversation while pi is streaming, the second `prompt` command will fail (pi errors when a prompt arrives during streaming without `streamingBehavior`).

**Assessment: Real gap.** PiProcess must track a `busy` flag. The Message Route checks it and returns HTTP 409 Conflict before touching the DB or pi. **Fixed in reconcile.**

### Critique 4: PiProcess stdout reader crash isolation

If the stdout reader coroutine hits an unexpected exception (e.g., JSON parse error on a corrupted line), the PiProcess becomes unresponsive to all future events.

**Assessment: Real gap.** The reader must catch per-line parse errors, log them, and continue. Only a pipe EOF or process death should terminate the reader. **Fixed in reconcile.**

### Critique 5: Partial assistant message on client disconnect

User sends a message → streaming starts → client disconnects → pi is aborted → partial text. Should the partial response be saved?

**Assessment:** Pi emits `message_end` with the authoritative final message even on abort (with `stopReason: "aborted"`). The backend should save whatever `message_end` reports. If `message_end` never arrives (process crash), save the accumulated text with a flag. **Not a gap — handled by existing design (save on message_end).**

### Critique 6: `bash` RPC command exists even with `--no-tools`

`--no-tools` disables the LLM's tool access, but the `bash` RPC *command* remains on the protocol. If the backend ever constructs a `bash` command (by bug or injection), it would execute.

**Assessment:** The backend must never send a `bash` command — this is a code discipline rule, not a runtime guard. An integration test (IT-6) verifies tools are disabled via `get_state`. The backend's PiProcess class should expose only `send_prompt`, `send_get_state`, `abort`, and `shutdown` — no generic "send any command" method. **Fixed in reconcile: restricted command API.**

### Critique 7: Database schema drift without Alembic

If a developer adds a column without a migration, the next fresh install gets a different schema than an upgraded install.

**Assessment:** Alembic is specified in `tech-env.md`. The initial migration creates both tables. Schema changes go through Alembic. The `metadata.create_all()` shortcut is only used in tests (test-scoped in-memory DB). **Not a gap — Alembic is already in the plan.**

### Critique 8: Frontend has no test coverage in the integration test list

The frontend components (C14–C19) are tested only by `npm run build` + `npm run lint`. No component tests verify that the SSE hook works or that the API client formats requests correctly.

**Assessment:** The e2e test (C22) exercises the full stack including the SSE stream, but it doesn't run a browser. A basic component test for the useStream hook (mock SSE responses) would catch integration bugs earlier. **Added to reconcile: unit test for useStream hook.**

---

## Reconcile

Changes folded from critique:

| Critique | Resolution | Affected components |
|---|---|---|
| C2 (session path) | Save `sessionFile` from `get_state` to `Conversation.pi_session_path`. Re-spawn with `--session <saved_path>`. | C5, C6, C10, C11 |
| C3 (concurrent prompts) | PiProcess tracks `is_streaming` state. Message Route returns 409 if busy. | C9, C10 |
| C4 (reader crash) | Stdout reader catches per-line JSON parse errors, logs, continues. Only EOF/death terminates. | C10 |
| C6 (bash command) | PiProcess exposes only named methods (`send_prompt`, `send_get_state`, `abort`, `shutdown`), not a generic send. | C10 |
| C8 (frontend tests) | Add a unit test for `useStream` hook with mocked SSE responses. | C18, C21 |

Post-reconcile, no identified gap remains unaddressed.

---

## Risk → Component Mapping

Every risk from `research.md` maps to a named component and at least one integration test:

| Risk | Component(s) | Integration Test(s) |
|---|---|---|
| R1: Async subprocess I/O | PiProcess (C10) | IT-3, IT-4 |
| R2: JSONL framing (U+2028) | PiProcess (C10) | IT-3 + dedicated unit test |
| R3: Tenant isolation gap | Repositories (C6, C7), Routes (C8, C9) | IT-2, IT-7 |
| R4: SSE disconnect lifecycle | Message Route (C9), PiProcess (C10) | IT-8 |
| R5: Pi process accumulation | ProcessManager (C11) | IT-6 (restart clears processes) |
| R6: agent_end vs agent_settled | PiProcess (C10), SSE Formatter (C12) | IT-4 |
| R7: Message POST vs process availability | ProcessManager (C11), PiProcess (C10) | IT-4 |
| R8: SQLite concurrent writes | Database (C4) | IT-9 (two tenants simultaneously) |

---

## Integration Test List

Each test exercises at least one cross-component seam. Every component (C1–C22) appears in at least one test.

| ID | Test | Seams exercised | Components | Validates |
|---|---|---|---|---|
| **IT-1** | **Identity stub rejects missing headers** | W2, W3 | C1, C3, C8 | Request without X-Tenant-ID or X-User-ID → 401. Request with both → Identity available in handler. |
| **IT-2** | **Conversation CRUD with tenant isolation** | W4, W5 | C1, C3, C6, C4, C5, C8, C13 | Tenant A creates a conversation. Tenant B cannot list, get, rename, or delete it (404, not 403). (C13: Alembic migrations run on test DB setup.) |
| **IT-3** | **Pi process spawns and streams** | W9, W10, W11 | C10, C11, C2 | Spawn a pi process, send `get_state`, verify response and `isStreaming: false`. Send a `prompt`, collect events through `agent_settled`. Verify at least one `text_delta` before `agent_settled`. |
| **IT-4** | **Message endpoint streams to client** | W6, W7, W8, W9, W10, W11, W12, W13, W14 | C1, C3, C9, C7, C11, C10, C12, C4, C5 | POST a message, read the SSE response. Assert: >1 text_delta chunk before done event. Assert: user message and assistant message saved in DB. |
| **IT-5** | **History survives process death** | W9 (re-spawn path), W14, W20 | C6, C7, C10, C11, C4, C5 | Send messages. Kill the pi process. Send another message. Verify the new pi process has history (the reply is context-aware). Verify messages in DB. |
| **IT-6** | **History survives backend restart** | W17, W18, W9 | C1, C4, C6, C7, C10, C11 | Send messages. Recreate the app (simulates restart — new ProcessManager, same DB file). List messages → still there. Send new message → pi reloads session, reply is context-aware. |
| **IT-7** | **Cross-tenant access refused on every endpoint** | W2, W3, W4, W5, W7 | C1, C3, C6, C7, C8, C9 | For each of: GET /conversations, GET /conversations/{id}, PATCH /conversations/{id}, DELETE /conversations/{id}, GET /conversations/{id}/messages, POST /conversations/{id}/messages — attempt with wrong tenant → 404. No data leaks in response body. |
| **IT-8** | **Client disconnect aborts pi** | W15, W10 | C9, C10, C12 | Start streaming a response. Close the HTTP connection mid-stream. Verify pi received `abort` and reached `agent_settled`. |
| **IT-9** | **Two tenants stream concurrently** | W8, W9, W10, W11, W13 | C1, C3, C9, C10, C11, C12, C4, C7 | Tenant A and Tenant B each send a message simultaneously. Both receive independent streamed replies. Neither sees the other's tokens. |
| **IT-10** | **Pi has no tools** | W10, W11 | C10, C11, C2 | Spawn pi process. Call `get_state`. Assert no tools in state (or verify system message has no tool declarations). |
| **IT-11** | **Frontend useStream hook** | W23 | C18, C19 | Unit test with mocked SSE response: verify delta accumulation, error handling, done detection. |
| **IT-12** | **Frontend build + render** | W21, W22, W24, W25 | C14, C15, C16, C17, C18, C19 | `npm run build` (typecheck + bundle), `npm run test` (component tests), manual dev-server check. Validates that frontend components compose and render without errors. |

**Coverage notes:** C20 (Makefile) is validated by running `make dev` / `make e2e` — it's orchestration, not logic. C21 (Backend tests) is the test suite itself — it's exercised by running it. C13 (Alembic) runs as part of every test that uses the DB (IT-2 onward).

**The e2e test (C22)** composes IT-2 through IT-10 into a single `pytest` run against a real backend with real Bedrock, matching the six "Done" criteria from `vision.md`:

| Done criterion | Covered by |
|---|---|
| Two tenants, each with a user | IT-2, IT-9 |
| Two conversations each, several messages, real Bedrock | IT-4, IT-9 |
| Streamed reply is incremental (>1 chunk) | IT-4 |
| History survives backend restart | IT-6 |
| Cross-tenant access refused on every endpoint | IT-7 |
| Agent has no file or shell tools | IT-10 |

---

## API Surface

### Endpoints

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| GET | `/api/conversations` | — | `[{id, title, created_at, updated_at}]` | Scoped to tenant from headers |
| POST | `/api/conversations` | `{title?}` | `{id, title, created_at}` | Creates conversation + pi session on first message |
| GET | `/api/conversations/{id}` | — | `{id, title, created_at, updated_at}` | 404 if wrong tenant |
| PATCH | `/api/conversations/{id}` | `{title}` | `{id, title, updated_at}` | 404 if wrong tenant |
| DELETE | `/api/conversations/{id}` | — | 204 | 404 if wrong tenant. Terminates pi process if alive. |
| GET | `/api/conversations/{id}/messages` | — | `[{id, role, content, created_at}]` | 404 if wrong tenant |
| POST | `/api/conversations/{id}/messages` | `{content}` | SSE stream (`text/event-stream`) | 404 if wrong tenant. 409 if conversation is busy. |

### SSE event types

```
data: {"type": "text_delta", "delta": "Hello"}
data: {"type": "status", "message": "Retrying in 2s..."}
data: {"type": "error", "message": "Model returned an error"}
data: {"type": "done", "message_id": "..."}
```

### Identity headers (the stub seam)

```
X-Tenant-ID: tenant-a
X-User-ID: user-1
```

Missing or empty → 401. The middleware is the ONE file a real auth integration replaces.

---

## Data Model

```sql
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,       -- UUID
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    pi_session_path TEXT,               -- set after first pi spawn
    created_at  TEXT NOT NULL,          -- ISO 8601
    updated_at  TEXT NOT NULL
);
CREATE INDEX ix_conversations_tenant ON conversations(tenant_id, updated_at DESC);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,   -- UUID
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,      -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL       -- ISO 8601
);
CREATE INDEX ix_messages_conversation ON messages(conversation_id, created_at);
```

Tenant isolation is enforced by the repository layer: every query that touches `conversations` includes `WHERE tenant_id = :tid`. Message queries join through `conversations` to pick up the tenant check. No query ever fetches by `conversation.id` alone.

---

## Key Design Decisions (from research, finalized here)

| Decision | Choice | Alternative considered | Why this one |
|---|---|---|---|
| Pi process topology | One process per conversation | Pool with session switching | Simplest, best crash isolation, no concurrency locking. ~50–100 MB/process is fine for local use. |
| History ownership | Dual: pi session = model context, app DB = display + metadata | App DB only (replay into pi) | Pi manages compaction/context natively. Replaying loses that. Each layer has one job. |
| Tenant separation of pi state | `--session-dir` per tenant | `PI_CODING_AGENT_DIR` per tenant | session-dir is sufficient; AGENT_DIR would also separate config, adding unnecessary complexity. |
| Streaming transport | SSE via POST response | WebSocket | One-way stream; no bidirectional need. SSE is simpler, native HTTP. |
| Session reload strategy | Save `sessionFile` path to DB, re-spawn with `--session <path>` | Use `--session-id` for lookup | Path-based is deterministic regardless of cwd; ID-based depends on cwd matching. |
| Concurrent prompt guard | PiProcess `is_streaming` flag → 409 on second prompt | Queue prompts with `streamingBehavior: "followUp"` | Simpler, no hidden queuing. User sees the conflict immediately. |
| Model selection | Configurable via `PI_MODEL` env var, default `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Hardcoded | Must be changeable without code changes; haiku is cheap for testing. |

---

## Project Layout

```
common_agent/                       ← workspace root
├── Makefile                        ← C20: dev, test, e2e targets
├── README.md                       ← operator docs
├── goal.md                         ← milestone contract
├── vision.md                       ← (intake, read-only)
├── tech-env.md                     ← (intake, read-only)
├── pi-notes.md                     ← (intake, read-only)
├── loop-docs/                      ← harness artifacts
│   ├── research.md
│   ├── architecture.md
│   ├── design.md
│   └── progress.md
├── src/
│   ├── backend/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   │       └── 001_initial.py
│   │   ├── app.py                  ← C1
│   │   ├── config.py               ← C2
│   │   ├── auth.py                 ← C3
│   │   ├── database.py             ← C4
│   │   ├── models.py               ← C5
│   │   ├── repositories.py         ← C6, C7
│   │   ├── pi_process.py           ← C10
│   │   ├── process_manager.py      ← C11
│   │   ├── sse.py                  ← C12
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── conversations.py    ← C8
│   │   │   └── messages.py         ← C9
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_conversations.py
│   │       ├── test_pi_process.py
│   │       ├── test_messages.py
│   │       └── e2e/
│   │           └── test_full.py    ← C22
│   └── frontend/
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx             ← C14
│           ├── api.ts              ← C19
│           ├── hooks/
│           │   └── useStream.ts    ← C18
│           ├── components/
│           │   ├── ConversationList.tsx  ← C15
│           │   ├── MessageThread.tsx     ← C16
│           │   └── MessageInput.tsx      ← C17
│           └── __tests__/
│               └── useStream.test.ts    ← IT-11
```

---

## Reviewer Decisions — RESOLVED, BINDING

A human reviewed this plan on 2026-10-05 and answered all three open questions. These are
final. Do NOT re-open, re-litigate, or "improve" them during BUILD. Where a decision
contradicts an earlier recommendation in this document, the decision below wins.

- **Pi process cwd — DECIDED: a stable per-conversation directory, NOT `/tmp`.**
  Each pi process runs with cwd `<DATA_DIR>/tenants/<tenant_id>/workdirs/<conversation_id>/`.
  The ProcessManager creates it on demand (`mkdir -p` semantics, idempotent) before spawning,
  and removes it when the conversation is deleted.
  This **overrides** the original `/tmp/pi-<conversation_id>` recommendation. Rationale: `/tmp`
  is cleaned by tmpfiles.d, reboots, and container restarts, and the resulting symptom — pi
  starting in a directory that no longer exists — is an obscure failure to diagnose. The
  simplification `/tmp` bought was a few lines of directory creation. Keeping the workdir
  under the same per-tenant prefix as the session dir also means all tenant state lives on one
  path, reinforcing the isolation story instead of introducing a second location scheme.
  The directory is expected to stay empty (tools are disabled). It must never contain a `.pi/`
  directory or `AGENTS.md`; the `-nc` / `--no-context-files` launch flag already disables that
  discovery regardless, and must be kept.

- **Auto-title generation — DECIDED: not in v1.** Conversations are created with the title
  `"New conversation"`. The rename endpoint is the only way a title changes. Do not add a
  second LLM call, do not derive a title from the first message or the first assistant
  response. Deferred deliberately; it is pure increment on top of a working shell.

- **Concurrent pi process cap — DECIDED: implement `MAX_PI_PROCESSES`, default 20.**
  The ProcessManager refuses to spawn beyond the cap and the request fails with **HTTP 503**
  and a clear error body; it does not queue and does not evict an active process. Configurable
  via the `MAX_PI_PROCESSES` env var alongside the other settings in `config.py`. Before
  refusing, the manager should first reap any processes already past their idle timeout — a
  request must not be rejected because of processes that were due for cleanup anyway. Add
  coverage that the cap triggers a 503 rather than an unbounded spawn.
