# pi agent — verified integration notes

Everything below was **executed against the real `pi` binary on this host**, not read off a
doc page. It de-risks the project's largest unknown: can a Python process drive pi against
Bedrock with streaming output and no tools? Yes. Here is exactly how.

Treat this as ground truth and a starting point, not as the architecture. The architecture
(process topology, session ownership, error handling) is still yours to design — see
`vision.md` → *Open questions*.

## Installed version

```
$ pi --version
1.0.2
```

Installed globally: `/usr/bin/pi`, package `@earendil-works/pi-coding-agent@1.0.2`.
Bundled docs: `/usr/lib/node_modules/@earendil-works/pi-coding-agent/docs/`.
Node on this host is 22.x (pi requires ≥ 22.19).

## The verified launch command

```bash
AWS_PROFILE=default pi --mode rpc --no-session --no-tools \
  --provider amazon-bedrock \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Why each flag:

| Flag | Why |
|---|---|
| `--mode rpc` | long-lived JSONL protocol on stdin/stdout; language-independent, so Python can drive it |
| `--no-tools` | disables every built-in tool (`read`, `bash`, `edit`, `write` are on by default). Required by `tech-env.md`. |
| `--provider amazon-bedrock` | the id is `amazon-bedrock`; `bedrock` is rejected |
| `--model us.…` | a cross-region inference profile id; bare catalog ids 400 on this account |
| `AWS_PROFILE=default` | **required** for pi to expose the Bedrock provider at all; credentials still come from the instance role |
| `--no-session` | used only for the probe. The real system almost certainly wants sessions — see open questions 2 and 3. |

## The probe (Python, works as-is)

```python
import json, os, subprocess

env = dict(os.environ, AWS_PROFILE="default")
p = subprocess.Popen(
    ["pi", "--mode", "rpc", "--no-session", "--no-tools",
     "--provider", "amazon-bedrock",
     "--model", "us.anthropic.claude-haiku-4-5-20251001-v1:0"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, bufsize=1, env=env, cwd="/tmp/pi-smoke")

def send(obj):
    p.stdin.write(json.dumps(obj) + "\n")
    p.stdin.flush()

send({"id": "1", "type": "get_state"})
send({"id": "2", "type": "prompt", "message": "Reply with exactly: rpc ok"})

deltas, seen = [], []
for line in p.stdout:
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    t = rec.get("type"); seen.append(t)
    if t == "response":
        print("RESPONSE", rec.get("command"), rec.get("success"))
    if t == "message_update":
        ev = rec.get("assistantMessageEvent") or {}
        if ev.get("type") == "text_delta":
            deltas.append(ev["delta"])
    if t == "agent_settled":
        break

print("STREAMED TEXT:", "".join(deltas).strip())
print("EVENTS:", " ".join(dict.fromkeys(seen)))
p.terminate()
```

Observed output:

```
RESPONSE get_state True
RESPONSE prompt True
STREAMED TEXT: rpc ok
EVENTS: response agent_start turn_start message_start message_end message_update turn_end agent_end agent_settled
```

Note this probe is deliberately simplistic in two ways the real backend must fix: it iterates
`p.stdout` (a line iterator — see the U+2028 prohibition in `tech-env.md`) and it blocks the
calling thread. Both are yours to do properly.

## Event sequence for one prompt

```
agent_start → turn_start → message_start
            → message_update × N   (assistantMessageEvent.type == "text_delta", .delta = text)
            → message_end → turn_end → agent_end → agent_settled
```

- The streamable text lives in `message_update.assistantMessageEvent.delta` when
  `assistantMessageEvent.type == "text_delta"`. Other `assistantMessageEvent` types exist
  (thinking, tool use) — check `message-types.md`.
- **`agent_end` is not the finish line.** `agent_settled` is. Queued follow-ups can produce
  more turns after `agent_end`.
- Note the event *ordering* above is the de-duplicated set in first-seen order, so
  `message_end` appears before `message_update` in that printout; the real stream interleaves
  `message_update`s between `message_start` and `message_end`.

## Protocol rules that bite

- **Framing:** one JSON object per line, split on `\n` **only**. Do not use a splitter that
  also breaks on U+2028 / U+2029 (Node's `readline`, Python's `str.splitlines()`) — model
  output can contain those characters and will corrupt your frames.
- **Correlation:** commands carry an optional `id`; the matching `response` repeats it. Use
  it. Without it you cannot tell which command a response belongs to under concurrency.
- **`response.success`** is the per-command ack. A `prompt` response also carries
  `data.disposition`, which tells you whether the prompt started a run, was queued, or was
  rejected — check it rather than assuming the run started.
- **stdout is the protocol.** pi's own logging goes to stderr. Capture stderr to a separate
  pipe/file; never merge it into stdout.
- **Backpressure:** respect it when writing to stdin; do not fire-and-forget a flood of
  commands.

## RPC command inventory (1.0.2)

Conversation: `prompt`, `steer`, `follow_up`, `abort`, `clear_queue`
Session: `new_session`, `switch_session`, `fork`, `clone`, `get_fork_messages`,
`set_session_name`, `get_session_stats`
Introspection: `get_state`, `get_messages`, `get_entries`, `get_tree`,
`get_last_assistant_text`, `get_commands`
Model: `set_model`, `get_available_models`, `set_thinking_level`
Other: `compact`, `bash`, `export_html`

`switch_session` / `new_session` existing on one process is precisely why open question 1
(process-per-conversation vs. a pool) is a real decision and not a formality. `bash` existing
as an RPC command is why the prohibition on exposing pi's surface to end users matters:
disabling tools does not remove the `bash` *command* from the protocol — your backend must
simply never send it.

## Flags worth knowing

- Tools: `-t/--tools <list>`, `-xt/--exclude-tools <list>`, `-nbt/--no-builtin-tools`,
  `-nt/--no-tools`. Defaults enabled: `read`, `bash`, `edit`, `write`.
- Sessions: `--session <path|id>`, `--session-id`, `--session-dir`, `--no-session`,
  `-n/--name`, `--fork`, `--continue`, `--resume`.
- Models: `--provider`, `--model`, `--models`, `--list-models`.
- Config dirs: `~/.pi/agent` globally (override with `PI_CODING_AGENT_DIR`), `.pi/` per
  project. Holds `settings.json`, `mcp.json`, `models.json`, `auth.json`, `AGENTS.md`.

## Known Bedrock failure, for your error-handling design

Using a bare catalog model id:

```
400 ValidationException: Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0
with on-demand throughput isn't supported. Retry your request with the ID or ARN of an
inference profile that contains this model.
```

pi surfaced this as an error message in the stream rather than by exiting. Your backend needs
a defined path for "pi emitted an error instead of text" — that is open question 5.
