# Vision — common_agent

## Problem & Users

- **Problem:** Teams want a ChatGPT-style web chat backed by *their own* agent runtime and
  *their own* cloud account, instead of a third-party SaaS. There is no reusable in-house
  shell: every attempt re-implements session handling, streaming, and tenant separation
  from scratch.
- **Primary user:** an end user of a tenant organization, opening a browser, holding several
  parallel conversations with an LLM agent and coming back to them later.
- **Secondary user:** the platform engineer who will host this for several tenant
  organizations at once and must be able to prove one tenant can never read another's data.
- **Today's workaround:** people use a public chat product (no control over data, model, or
  agent behavior) or a local terminal agent (no multi-user, no browser, no history).

## What we're building (the ONE feature)

A web chat application with a Python backend that wraps the **pi agent** as its LLM runtime.
A signed-in user sees a list of their conversations, opens one, sends a message, and watches
the assistant's reply stream in token by token. Conversations persist across page reloads and
restarts. Every conversation belongs to exactly one tenant and one user, and the data layer
enforces that. The agent is **conversation-only** in this version: pi's built-in file and
shell tools are fully disabled.

This is the reusable shell — a correct, streaming, multi-tenant, multi-session chat over a
pi-based agent. Agent *capabilities* (tools, retrieval, memory) are deliberately a later
milestone; getting the shell right is this goal.

## Expected outcomes (user action → system response)

- A user opens the app → sees only their own conversation list, newest first
- A user creates a new conversation → an empty conversation appears and becomes active
- A user sends a message → the assistant's reply streams into the page incrementally, not as
  one delayed block
- A user reloads the page → the conversation and its full message history are still there
- A user renames or deletes a conversation → the change persists
- A user switches between conversations → each keeps its own independent history and context
- A request carrying tenant B's identity asks for tenant A's conversation → the API refuses
  it (not found / forbidden), and nothing of A's leaks into the response
- Two users send messages at the same time → both get their own streamed replies; neither
  sees the other's tokens

## Done =

A reviewer can run **one documented command** to start the whole system locally, and **one
documented command** to run an automated end-to-end test that:

1. creates two tenants, each with a user
2. has each user create two conversations and exchange several messages, with the replies
   coming from a real Amazon Bedrock model through pi
3. asserts the streamed reply arrived incrementally (more than one chunk observed before
   completion), not as a single final blob
4. asserts history survives a backend restart
5. asserts every cross-tenant access attempt is refused, for every endpoint that takes a
   conversation or message id
6. asserts the agent has no file or shell tools available

"Code exists" is not done. "The test above passes against a real Bedrock-backed pi" is done.

## Scope

- **In:** the chat web UI (conversation list, message thread, streaming, new/rename/delete);
  the Python API; the pi integration; persistence of conversations and messages; the tenant
  isolation enforcement and its tests; local start + the end-to-end test; a short operator
  README.
- **Out (deferred, do NOT build):**
  - real authentication — see *Non-negotiables*; identity is a deliberate, replaceable stub
  - agent tools of any kind, retrieval/RAG, file upload, multimodal input
  - cloud deployment, IaC, containers for production, CI pipelines
  - billing, quotas, rate limiting, usage analytics, admin console
  - organization/team management beyond the tenant id a request carries
  - model picker UI, prompt templates, system-prompt editing per tenant

## Success bar & non-negotiables

- **Success looks like:** an engineer who was not part of this run can clone the repo, follow
  the README, have it running in minutes, and see where to plug in real authentication and
  the first agent tool — because both are isolated behind a named seam, not sprinkled through
  the code.
- **Non-negotiables:**
  - **Identity is a stub, and it must look like one.** Tenant and user identity enters the
    system through exactly ONE replaceable component. In development it may be read from a
    request header. It must be obvious, documented, and covered by tests that a real
    authenticator drops into that one place. Do NOT hand-roll password hashing, token
    signing, or a login UI — that is a later milestone, and a half-built one is worse than an
    honest stub.
  - **Tenant isolation is NOT a stub.** Every read and write of conversation or message data
    is scoped by tenant id at the data-access layer, not only by a check in a route handler.
    Isolation has dedicated tests that attempt cross-tenant access on every such endpoint.
  - **The agent has no tools.** pi runs with its built-in tools disabled. A test asserts this.
  - **Streaming is incremental, end to end.** No endpoint may buffer a whole reply and send it
    at once. The test asserts chunking.
  - **No AWS credentials in code, config files, or logs.** Ambient credentials only.
  - **The agent must never deploy anything or create cloud resources.** Bedrock model
    inference calls are the only AWS calls this project makes.

## Open questions

These are for RESEARCH to resolve against the real pi runtime and record in `research.md`;
PLAN must then commit to an answer in `architecture.md`. Do not guess silently.

1. **pi process topology.** pi RPC mode is a long-lived subprocess that holds one active
   session at a time but can `new_session` / `switch_session` / `fork`. What is the right
   mapping from (tenant, user, conversation) to pi processes? One process per conversation,
   a pooled set of processes with session switching, or one process per request? Consider
   concurrency (two users at once), memory, cold-start latency, crash isolation between
   tenants, and what happens to an in-flight run when a client disconnects. Justify the
   choice; name what would make you change it.
2. **Where conversation history lives.** pi persists its own session files (`--session-dir`,
   see `session-format.md`). The application also needs conversation metadata (owner, tenant,
   title, timestamps). Is pi's session file the system of record for message content, with the
   app DB holding only metadata and a pi session id? Or does the app DB own messages too,
   with pi sessions treated as disposable? Decide explicitly — a half-and-half answer is how
   history silently diverges from what the model actually saw.
3. **Tenant separation of pi state.** If pi session files are involved, how are they
   partitioned so one tenant's files are unreachable from another's session? (`--session-dir`
   per tenant, `PI_CODING_AGENT_DIR` per tenant, both?)
4. **Transport for streaming.** SSE is the expected fit for a one-way token stream and is
   preferred unless research finds a concrete reason otherwise. If you choose WebSocket,
   argue why in `architecture.md`. Either way, state how an aborted/disconnected stream
   cancels the underlying pi run (pi RPC has an `abort` command).
5. **pi failure surface.** What does the backend do when the pi subprocess dies mid-run,
   when Bedrock throttles, or when pi emits an `errorMessage` instead of text (we have
   already seen one: a model id that needs an inference profile)? Where is that surfaced to
   the user, and what does the retry policy look like?
6. **pi version pinning.** `pi 1.0.2` is what is installed and verified. How is that version
   pinned and recorded so a later pi release cannot silently change the RPC event shapes this
   project parses?
