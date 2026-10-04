# Technical Environment — common_agent

This file is AUTHORITATIVE. Where it names a choice, that choice is settled — do not
re-litigate it in RESEARCH or PLAN. Where it says "research decides", it is genuinely open.

## Summary

| Attribute | Value |
|---|---|
| Project type | Greenfield. The repo is empty (`git init`, no commits). |
| Language / runtime | Python 3.11+ (backend), Node 22+ / TypeScript (frontend) |
| Package manager | `uv` for Python, `npm` for the frontend |
| Deploy target | **none — local only.** No cloud resources, no IaC, no CI. |
| LLM access | Amazon Bedrock, via the pi agent, via this host's ambient IAM role |

## Frameworks & services

| Layer | Choice |
|---|---|
| API | FastAPI + `uvicorn` (async; needed for streaming) |
| Agent runtime | **pi agent `1.0.2`**, driven as a **subprocess in RPC mode** (`pi --mode rpc`) |
| LLM provider | Amazon Bedrock (pi provider id `amazon-bedrock`) |
| Persistence | SQLite file + SQLAlchemy 2.x (async) + Alembic for schema |
| Frontend | React 18 + TypeScript + Vite |
| Frontend styling | Tailwind CSS |
| Backend tests | `pytest` + `pytest-asyncio`, `httpx` ASGI client |
| End-to-end test | `pytest` driving the real backend + real pi + real Bedrock (see `vision.md` → Done) |
| Local orchestration | One documented command to bring up frontend + backend. Prefer plain scripts (`Makefile` / `npm` scripts); docker-compose is acceptable but must not be required for the e2e test. |

The **pi integration is NOT the in-process TypeScript SDK.** The backend is Python and owns
the pi process lifecycle over stdin/stdout JSONL. This is settled.

## pi + Bedrock — verified facts, do not re-derive

These were established by running the real binary on this host. Treat them as constraints;
re-deriving them costs a turn and a Bedrock bill. Full detail and a working Python probe are
in **`pi-notes.md`** at the workspace root — read it before writing any pi code.

1. The pi provider id is **`amazon-bedrock`**. `--provider bedrock` fails with
   `Unknown provider "bedrock"`.
2. **`AWS_PROFILE` must be set in pi's environment** (e.g. `AWS_PROFILE=default`) or pi will
   not expose the Bedrock provider at all and reports `No models available` — even though the
   actual credentials come from the attached instance role, not the profile. Pass it
   explicitly in the subprocess environment.
3. Model ids must be **cross-region inference profile ids with the `us.` prefix**. A bare
   catalog id returns HTTP 400: `Invocation of model ID ... with on-demand throughput isn't
   supported. Retry your request with the ID or ARN of an inference profile`. Verified
   working: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
4. Region comes from ambient `AWS_REGION` / `AWS_DEFAULT_REGION` (`us-west-2` on this host).

## Prohibitions

- **Do not deploy anything.** No CloudFormation/CDK/Terraform, no ECR/ECS/Lambda/S3/EC2,
  no `aws` CLI calls that create, modify, or delete resources. Bedrock model *inference* is
  the only AWS API this project may call.
- **Do not enable any pi tool.** Run pi with its built-in tools disabled (`--no-tools`, or
  the narrower `-nbt`/`-xt` forms — see `cli.md`). Under no circumstances may an end-user
  message reach pi's `bash`, `write`, or `edit` tools. A test must assert this.
- **Do not write AWS credentials** into source, config, `.env` files committed to git, logs,
  or error responses. Ambient credentials only. Never log the subprocess environment.
- **Do not modify this host's global pi config** (`~/.pi/agent`, `~/.pi/agent/settings.json`,
  `auth.json`). If pi config is needed, scope it to the project via `PI_CODING_AGENT_DIR` or
  a project-local `.pi/` directory, and document it.
- **Do not implement real authentication.** No password hashing, no JWT signing, no OAuth, no
  login page. Identity is a single replaceable dependency; see `vision.md` →
  *Non-negotiables*. Anything that looks like real auth but isn't is the failure mode here.
- **Do not use `readline` (Node) or any line splitter that breaks on U+2028/U+2029** for pi's
  JSONL stream. Split on `\n` only. In Python, iterating the pipe or `splitlines()` is also
  unsafe for the same reason — `splitlines()` splits on U+2028/U+2029 and more. Split
  explicitly on `b"\n"` / `"\n"`.
- **Do not treat `agent_end` as "the turn is finished."** Wait for `agent_settled`.
- **Do not print anything but protocol JSONL on pi's stdout assumptions** — pi's stdout is
  the protocol; its logs go to stderr. Capture stderr separately, never interleave.
- Do not add Redis, Celery, Kafka, Kubernetes, or a message broker. If you believe
  concurrency requires one, raise it under `## Questions for reviewer` instead of adding it.
- Do not add a second database. One SQLite file.

## Validation commands

The agent must run these and fix failures before checking off a milestone.

```bash
# Backend — from the backend package root
uv run pytest -q                      # unit + integration tests
uv run ruff check .                   # lint (configure a rule set; do not blanket-ignore)
uv run mypy .                         # types, if a mypy config is established

# Frontend — from the frontend package root
npm run build                         # must typecheck and build clean
npm run test                          # component/unit tests
npm run lint

# pi reachability smoke test (proves provider + model + credentials are live)
AWS_PROFILE=default pi --mode json --no-session --no-tools \
  --provider amazon-bedrock --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  -p "Reply with exactly: bedrock ok"

# The Done gate — the two-tenant multi-session streaming e2e test
# (the exact invocation is part of what this project must define and document)
```

## Reference material (pinned)

pi's published docs are the system of record for the RPC protocol. Prefer the **raw
markdown** over the rendered site — the site is client-rendered and fetches poorly.

- Locally bundled copies (fastest, matches the installed 1.0.2):
  `/usr/lib/node_modules/@earendil-works/pi-coding-agent/docs/`
- Canonical raw markdown:
  `https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/<page>.md`
  where `<page>` ∈ `rpc`, `rpc-commands`, `json`, `message-types`, `sessions`,
  `session-format`, `providers`, `models`, `cli`, `settings`, `security`, `tools`
- Model catalog: <https://pi.dev/models>
- Rendered docs home: <https://pi.dev/docs/latest>

Read `rpc.md`, `rpc-commands.md`, and `message-types.md` in full before designing the pi
integration. Read `sessions.md` + `session-format.md` before answering `vision.md` open
question 2 or 3.
