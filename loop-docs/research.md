# Research — common_agent

## Intake Sufficiency

The intake (`vision.md`, `tech-env.md`, `pi-notes.md`) is **sufficient** to proceed. All load-bearing inputs are present:

| Element | Status | Source |
|---|---|---|
| Goal | Clear — multi-tenant streaming chat backed by pi agent | `vision.md` §What we're building |
| Success criteria | Specific, testable — 6-point e2e test against real Bedrock | `vision.md` §Done |
| Hard constraints | Exhaustive — no real auth, no tools, tenant isolation at data layer, streaming e2e, ambient creds only, no cloud resources | `vision.md` §Non-negotiables + `tech-env.md` §Prohibitions |
| Tech stack | Fully specified — FastAPI/uvicorn, React 18/TS/Vite/Tailwind, SQLite/SQLAlchemy 2.x/Alembic, pi 1.0.2 RPC subprocess | `tech-env.md` §Frameworks |
| Pi integration ground truth | Verified probe with working Python code, event sequence, protocol rules | `pi-notes.md` |
| Validation commands | Defined for backend (`pytest`, `ruff`, `mypy`), frontend (`npm build/test/lint`), pi smoke test, and e2e | `tech-env.md` §Validation |

**No blocking gaps.** All six open questions from `vision.md` are resolved below.

---

## Open Question 1: Pi Process Topology

**Decision: One pi process per conversation.**

### Evidence

- pi RPC mode is a long-lived subprocess holding one active session at a time (`rpc.md` lines 1–4).
- `switch_session` exists but cannot be issued while a prompt is running — the process must be idle (`rpc-commands.md` §Session; a prompt in flight blocks the session switch until `agent_settled`).
- Each pi process is a Node.js runtime (~50–100 MB RSS). For a local-only deployment targeting a handful of concurrent conversations, 10–20 processes consume 0.5–2 GB — well within a dev machine.

### Design

- **Spawn** a pi process on the first message sent to a conversation. The process owns that conversation's pi session for its lifetime.
- **Idle timeout**: terminate the process after N minutes of inactivity (configurable, e.g. 15 min). On the next message, re-spawn with `--session <path>` to reload history.
- **Concurrency**: two users messaging simultaneously get independent processes — no locking, no session switching.
- **Crash isolation**: a crash in one conversation's pi process cannot affect any other conversation. The session file survives on disk; a new process can reload it.
- **Client disconnect**: detect via SSE connection drop → send `{"type": "abort"}` to pi's stdin → let pi settle → keep or terminate the process based on idle policy.

### What would change this

If the system needed hundreds of concurrent conversations (production multi-tenant at scale), a pooled approach with session switching would reduce memory. That is explicitly out of scope (`tech-env.md`: local only, no cloud deployment).

---

## Open Question 2: Where Conversation History Lives

**Decision: Dual storage — pi session file is the model's system of record; app DB stores messages for display and metadata.**

### Evidence

- Pi session files are append-only JSONL containing the full conversation tree, compaction summaries, and branch state (`session-format.md`). This is what the model actually sees.
- The `get_messages` RPC command returns all messages from the active session (`rpc-commands.md` line 190–205), but only when the pi process is running.
- The app needs metadata pi doesn't track: tenant_id, user_id, conversation title, timestamps, sort order.

### Design

- **Pi session file** = model-context layer. Pi manages compaction, context windows, and what the model "remembers." The backend never modifies session files directly.
- **App SQLite DB** = display + metadata layer. Tables: `conversations` (id, tenant_id, user_id, title, pi_session_path, created_at, updated_at) and `messages` (id, conversation_id, role, content, created_at). Messages are captured as they stream and written to the DB for fast UI rendering.
- **On restart**: a new pi process loads the session file via `--session <path>`. The UI loads message history from the app DB. No need to parse JSONL session files for display.
- **If they diverge**: pi's session is authoritative for model context. The app DB messages are a display cache — worst case, they can be rebuilt from pi's session file via `get_messages`.

This avoids the anti-pattern `vision.md` warns about: each layer has one clear purpose. The pi session is not "also a display store" and the app DB is not "also a model context."

---

## Open Question 3: Tenant Separation of Pi State

**Decision: `--session-dir` per tenant.**

### Evidence

- `--session-dir <dir>` controls where pi reads and writes session files (`cli.md` lines 96–97, `sessions.md` line 50).
- Pi session file paths are deterministic: `<session-dir>/--<cwd-path>--/<timestamp>_<session-id>.jsonl` (`session-format.md` lines 10–11).
- `PI_CODING_AGENT_DIR` overrides the *config* directory, not just sessions (`environment-variables.md` line 81). Using it per-tenant would also separate settings, which is unnecessary overhead.

### Design

- Each pi process is launched with `--session-dir <data_root>/tenants/<tenant_id>/sessions/`.
- Tenant A's session files are physically unreachable from a process started with tenant B's `--session-dir`.
- Combined with one-process-per-conversation (Q1), a pi process can only ever see its own tenant's files — it never `switch_session` to another tenant's path.
- The app DB enforces tenant scoping independently: every query filters by `tenant_id`.

Two layers of isolation: filesystem path separation (pi level) + query scoping (app DB level).

---

## Open Question 4: Transport for Streaming

**Decision: SSE (Server-Sent Events).**

### Evidence

- The stream is one-directional: server→client token deltas. SSE is designed for exactly this pattern.
- User messages are discrete actions (POST a message), not a continuous bidirectional stream.
- SSE works over standard HTTP — no upgrade negotiation, works through proxies, native browser `EventSource` API or `fetch` with `ReadableStream`.
- FastAPI supports SSE via `StreamingResponse` with `text/event-stream` content type — no extra library needed.
- `vision.md` line 119: "SSE is the expected fit… preferred unless research finds a concrete reason otherwise." No reason found.

### Design

- `POST /api/conversations/{id}/messages` — sends the user message, returns immediately with the message record.
- `GET /api/conversations/{id}/messages/{id}/stream` — SSE endpoint that streams the assistant reply as `data: {"type": "text_delta", "delta": "..."}` events, ending with a `data: {"type": "done", ...}` event.
- Alternative: a single `POST` that itself returns an SSE stream (simpler, avoids a race between "message created" and "start listening"). The architecture should pick one.
- **Abort on disconnect**: FastAPI/Starlette detects client disconnect (`Request.is_disconnected()` or exception on write). The handler then sends `{"type": "abort"}` to pi's stdin and waits for `agent_settled`.

### Why not WebSocket

WebSocket adds connection lifecycle management, reconnection logic, and message routing complexity for no benefit — we have no client→server streaming requirement.

---

## Open Question 5: Pi Failure Surface

**Decision: Lean on pi's built-in retry for provider errors; add process-level crash recovery and user-visible error surfacing.**

### Evidence — failure modes from the docs

| Failure | Pi behavior | Source |
|---|---|---|
| Bedrock throttle (429/529) | Pi auto-retries with backoff; emits `auto_retry_start`/`auto_retry_end` events | `json.md` §Retry events |
| Bedrock error (e.g. wrong model id) | Pi emits `message_end` with `stopReason: "error"` and `errorMessage` on the assistant message | `message-types.md` line 134, `pi-notes.md` §Known Bedrock failure |
| Pi subprocess crash | Process exits; stdout pipe hits EOF | `rpc.md` §Errors line 86–89 |
| Malformed command to pi | `response.success: false` with error message | `rpc.md` §Errors line 75–80 |
| Provider stream error mid-response | `assistantMessageEvent.type == "error"` with `reason` and `error` fields | `json.md` §Reconstruct streaming messages, line 89 |

### Design

1. **Provider errors (throttle, model errors)**: Forward pi's `auto_retry_start` events to the client as SSE status events ("Retrying in 2s..."). On final failure (`auto_retry_end.success: false` or `stopReason: "error"`), send an SSE error event with the `errorMessage` and close the stream.

2. **Pi process crash**: Detect via EOF on stdout or non-zero exit code. Send an SSE error event to the client ("The assistant encountered an error. Please try again."). Mark the process as dead in the process manager. On next message, spawn a new process with `--session <path>` to reload history.

3. **Timeout**: If the backend receives no events from pi for a configurable duration (e.g. 60s), send `abort`, report a timeout error to the client.

4. **No application-level retry of prompts** — avoid double-spending tokens. The user can resend manually.

5. **Error response shape**: Every SSE stream can emit `{"type": "error", "message": "..."}` as a terminal event. The frontend displays it inline in the message bubble.

---

## Open Question 6: Pi Version Pinning

**Decision: Runtime version check on backend startup + documented version requirement.**

### Evidence

- pi 1.0.2 is installed globally at `/usr/bin/pi` (`pi-notes.md` line 18).
- The RPC event shapes, command names, and session format are all version-specific.
- pi is a global npm package, not a Python dependency — it can't be pinned in `pyproject.toml`.

### Design

- **Startup check**: The backend runs `pi --version` on startup and refuses to start (or logs a warning) if the output is not `1.0.2`.
- **Documentation**: The operator README states the required pi version and how to install it: `npm install -g @earendil-works/pi-coding-agent@1.0.2`.
- **Configuration**: The expected version is a constant in the backend config, not a magic string scattered through the code.
- **Future**: When pi 1.1 ships, the backend maintainer updates the constant and adjusts any changed RPC shapes. The startup check prevents silent drift.

---

## Decisions (assumptions made without human input)

These are non-obvious choices made to unblock autonomous execution. A reviewer may override any of them.

| # | Decision | Rationale |
|---|---|---|
| D1 | Default model for chat: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (configurable via env var) | Only model verified on this host. Haiku is cheap for a chat shell; the model is a config knob, not hardcoded. |
| D2 | Pi process idle timeout: 15 minutes default | Balances memory (don't keep idle processes forever) vs. latency (don't cold-start on every message in an active conversation). Configurable. |
| D3 | Identity stub: `X-Tenant-ID` and `X-User-ID` request headers | Simplest replaceable stub. A single middleware reads them and populates a request-scoped context object. The seam is one file/class. Documented as "replace this with your auth middleware." |
| D4 | Single POST endpoint returns SSE stream for message send | `POST /api/conversations/{id}/messages` accepts the user message body and returns `Content-Type: text/event-stream`. Avoids the race between creating a message and subscribing to its stream — one request does both. |
| D5 | Pi working directory: a temp directory per conversation, not the project root | Pi's cwd controls resource discovery and tool paths. Since tools are disabled, cwd doesn't matter for tool execution. Using a temp dir per conversation avoids pi discovering any project `.pi/` config or `AGENTS.md` that might exist in the workspace. |
| D6 | Frontend dev server proxies API requests to backend | Vite's `proxy` config forwards `/api/*` to `localhost:8000`. One `npm run dev` + one `uvicorn` command. A Makefile target runs both. |
| D7 | Use `asyncio.create_subprocess_exec` for pi process management | Async subprocess is required to avoid blocking the event loop. Read stdout/stderr via `asyncio.StreamReader`, split on `b"\n"` only. |
| D8 | The `bash` RPC command is never sent by the backend | `--no-tools` disables the LLM's ability to call tools, but the `bash` RPC command still exists on the protocol (`pi-notes.md` line 139). The backend must never construct or send a `bash` command. The e2e test should verify this by checking that the pi process's enabled tools list is empty (via `get_state` or by inspecting the system message). |

---

## Risks the Plan Must Address

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Async subprocess I/O complexity** — Python's asyncio subprocess + pipe reading is notoriously tricky (deadlocks, buffering) | Backend hangs or drops events | Use `asyncio.create_subprocess_exec` with explicit `asyncio.StreamReader`. Read stdout in a dedicated coroutine. Never use `p.stdout.readline()` synchronously. Test with real pi early (milestone 1, not milestone N). |
| R2 | **JSONL framing bug** — splitting on anything other than `\n` corrupts frames when model output contains U+2028/U+2029 | Silent message corruption | Enforce: split on `b"\n"` only. Add a unit test with a payload containing U+2028. `tech-env.md` and `pi-notes.md` both warn about this. |
| R3 | **Tenant isolation gap** — a route handler forgets to scope by tenant_id | Cross-tenant data leak | Enforce at the data-access layer (repository pattern), not in route handlers. Every DB query method takes `tenant_id` as a required parameter. The e2e test hits every endpoint with cross-tenant credentials. |
| R4 | **SSE connection lifecycle** — client disconnects not detected, leaving orphan pi processes running | Memory leak, wasted Bedrock tokens | Use `Request.is_disconnected()` polling in the SSE loop, or catch `ConnectionResetError`/`ClientDisconnect` on write. Send `abort` to pi on detection. |
| R5 | **Pi process accumulation** — no idle cleanup, processes pile up | OOM on dev machine | Implement an idle timeout in the process manager. Log process count on spawn/cleanup. The process manager is a first-class component, not an afterthought. |
| R6 | **`agent_end` vs `agent_settled` confusion** — treating `agent_end` as the end of a turn | Missing final tokens or follow-up turns | Wait for `agent_settled` before closing the SSE stream. Both `tech-env.md` and `pi-notes.md` explicitly warn about this. |
| R7 | **Race: message POST vs. pi process availability** — user sends a message before the pi process is ready | 500 error or lost message | The process manager's `get_or_create` is async and waits for the process to be ready (first `response` to a `get_state` command) before accepting prompts. |
| R8 | **SQLite concurrent writes** — two requests writing at the same time | Database locked errors | Use WAL mode (`PRAGMA journal_mode=WAL`). SQLite with WAL handles concurrent reads + one writer well. For a local-only app with a handful of users, this is sufficient. |
