# common_agent

A multi-tenant web chat application backed by the [pi agent](https://github.com/anthropics/pi) running on Amazon Bedrock. Users hold streaming conversations with an LLM; conversations persist across restarts; tenant isolation is enforced at the data layer.

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python3.11` must be on PATH |
| Node.js | 22+ | For the frontend build |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| pi | 1.0.2 | `pi --version` must report `1.0.2` |
| AWS credentials | — | Ambient credentials via `AWS_PROFILE=default`; must have Bedrock model access |

## Setup

```bash
# Install backend dependencies
cd src/backend && uv sync --all-extras && cd ../..

# Install frontend dependencies
cd src/frontend && npm install && cd ../..
```

Or use the Makefile:

```bash
make install
```

## Running

```bash
# Start both backend (port 8000) and frontend (port 5173)
make dev

# Or start individually:
make dev-backend   # uvicorn on :8000
make dev-frontend  # vite on :5173
```

Open http://localhost:5173 in a browser.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `PI_MODEL` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model ID passed to pi |
| `DATA_DIR` | `./data` | Where SQLite DB, pi sessions, and workdirs live |
| `PI_IDLE_TIMEOUT_SECONDS` | `900` | Seconds before an idle pi process is reaped |
| `MAX_PI_PROCESSES` | `20` | Maximum concurrent pi processes; over-cap returns 503 |

## Testing

```bash
# All tests (backend + frontend)
make test

# Backend only (unit + integration, hits real Bedrock)
make test-backend

# Frontend only (vitest)
make test-frontend

# Lint
make lint

# End-to-end (the "Done" gate — real Bedrock required)
make e2e
```

## Architecture

```
Browser → Vite proxy → FastAPI → Identity middleware → Routes
                                                         ├─ Conversation CRUD → SQLite
                                                         └─ Message send → ProcessManager → pi subprocess (RPC)
                                                                                              └─ Amazon Bedrock
```

- **Backend:** FastAPI + async SQLAlchemy 2.x + aiosqlite (SQLite with WAL mode)
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **LLM runtime:** pi agent in RPC mode, one subprocess per conversation
- **Streaming:** SSE via POST response (`text/event-stream`)

## Auth seam — how to replace the identity stub

Authentication is deliberately a stub. The entire auth surface is in **one file**: `src/backend/auth.py`.

The current stub reads `X-Tenant-ID` and `X-User-ID` from request headers. To plug in real authentication:

1. Replace `IdentityMiddleware` in `auth.py` with your authenticator (JWT validation, OAuth token exchange, session cookie, etc.)
2. It must set `request.state.identity` to an `Identity(tenant_id, user_id)` — the rest of the app reads only that dataclass
3. Update `get_identity()` if the injection point changes
4. Run `make test` to verify tenant isolation still passes

No other file needs to change. The identity stub is covered by `test_auth.py` (IT-1).

## Agent tools — how to extend

Pi runs with `--no-tools` (all built-in tools disabled). To enable tools:

1. Remove `--no-tools` from the command in `src/backend/process_manager.py` (`get_or_create` method)
2. Optionally add `--allowedTools` with a specific tool list instead of enabling all tools
3. Update or remove the IT-10 no-tools assertion in `tests/test_pi_process.py`
4. Be aware that enabling tools means pi can execute code and write files in the conversation's workdir (`DATA_DIR/tenants/<tid>/workdirs/<cid>/`)

## Project layout

```
├── Makefile                    # dev, test, e2e, lint targets
├── README.md                   # this file
├── src/
│   ├── backend/
│   │   ├── app.py              # FastAPI factory + lifespan
│   │   ├── auth.py             # Identity stub (THE auth seam)
│   │   ├── config.py           # Environment-driven settings
│   │   ├── database.py         # SQLAlchemy engine + session factory
│   │   ├── models.py           # Conversation + Message ORM
│   │   ├── repositories.py     # Tenant-scoped data access
│   │   ├── pi_process.py       # Single pi subprocess wrapper
│   │   ├── process_manager.py  # Conversation→PiProcess mapping
│   │   ├── sse.py              # SSE event formatter
│   │   ├── routes/
│   │   │   ├── conversations.py
│   │   │   └── messages.py
│   │   └── tests/
│   │       ├── test_auth.py
│   │       ├── test_conversations.py
│   │       ├── test_messages.py
│   │       ├── test_pi_process.py
│   │       └── e2e/test_full.py
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx
│       │   ├── api.ts
│       │   ├── hooks/useStream.ts
│       │   └── components/
│       │       ├── ConversationList.tsx
│       │       ├── MessageThread.tsx
│       │       └── MessageInput.tsx
│       └── package.json
└── goal.md                     # milestone contract (dev artifact)
```
