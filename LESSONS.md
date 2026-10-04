# Lessons Learned

Technical lessons discovered during prior runs, as **Trigger / Symptom / Fix**
entries. The coding agent reads this before designing and building; check your
work against it before a gate.

> **The entry bar — a lesson is *residue*, not a fact.** Add a lesson only for what
> no doc, tool, or introspection surfaces without paying the failure cost: an
> undocumented gotcha, a version/behavior trap, a surprise you had to *discover*. If
> a doc, a `--help`, or a `boto3`/service-model introspection answers it, it is **not**
> a lesson — link the source and let the next run re-fetch it (a copied API signature
> or published default just drifts). Keeping this bar is what stops the seed from
> bloating into stale, contradicting-the-docs tech debt.

> This is the compounding surface of the harness. When a run hits a trap and fixes
> it, add the lesson here (structured, not prose) so the *next* run never repeats it.
> Run `sdharness compound <run-dir>` to promote a finished run's `progress.md`
> `## Patterns` into this file (a curator agent semantically dedups + applies the bar
> above by default; `--deterministic` for offline title-dedup — review the diff either
> way). In a team, promote durable lessons into the shared seed via review. See
> `docs/concepts/compound-engineering.md`.

## Patterns

<!-- General truths. Check every project against these. -->

### Prove the wiring, not just the parts

**Trigger:** A multi-component design where each component has unit tests.
**Symptom:** Every unit test passes; the system still fails because component A was
never actually wired to component B (a declared dependency nothing invokes).
**Fix:** In PLAN, name every cross-component seam explicitly and add an integration
test for it. In VERIFY, exercise every seam end-to-end with cited evidence before
reporting `status: passed`.

### A checkbox needs evidence, not optimism

**Trigger:** Checking off a `goal.md` milestone at the end of a turn.
**Symptom:** A box flipped to `- [x]` but the validation was never run (or failed),
so later turns build on a false foundation.
**Fix:** Run the milestone's stated validation, show its output, and log the outcome
in `progress.md` the same turn. No passing command → leave the box unchecked.

## Gotchas

<!-- Stack-specific. Apply when the trigger matches. -->

<!-- Example (delete/replace for your stack):
### <one-line title>
**Trigger:** <the situation that causes it>
**Symptom:** <what you observe>
**Fix:** <the concrete correction>
-->

<!-- The two below are the RESIDUE for AWS Lambda MicroVMs: undocumented footguns the
docs would actively MISLEAD you on. Everything else about MicroVMs (the API shapes, the
image recipe, the least-privilege IAM) is in the current AWS docs — read those in RESEARCH
(see examples/mini-factory-aws/tech-env.md), don't transcribe them here. -->

### MicroVM build-role PassRole must NOT be conditioned on iam:PassedToService

**Trigger:** Granting the caller `iam:PassRole` on the **build role** used by the image bake,
and (reasonably) scoping it with a `iam:PassedToService=lambda.amazonaws.com` condition — the
way you'd correctly scope the *execution*-role PassRole for the run.
**Symptom:** The bake fails with `not authorized to perform: iam:PassRole … no identity-based
policy allows` even though the grant looks correct. The docs' least-privilege example suggests
the condition, so you'd add it and be misled.
**Fix:** **Asymmetry the docs don't call out:** the run operation populates the
`iam:PassedToService` context key (so the execution-role PassRole *can* be conditioned), but the
**create-image (bake) operation does NOT populate it** — a conditioned build-role PassRole
silently denies. Scope the build-role PassRole by **Resource ARN only** (the role's own trust
policy bounds who may assume it). Mirror-image trap: don't *pre-check* a conditioned PassRole with
a context-less `iam:simulate_principal_policy` either — it returns `implicitDeny` and false-skips a
capable account. Prefer attempt-and-catch `AccessDenied`.

### MicroVM operations authorize under the `lambda:` action prefix, not `lambda-microvms:`

**Trigger:** Writing the caller IAM policy for the MicroVM operations, and (reasonably) using the
client name as the action prefix — `lambda-microvms:CreateMicrovmImage`, `lambda-microvms:RunMicrovm`, etc.
**Symptom:** Every MicroVM call returns `AccessDenied` despite a policy that "obviously" grants the
operations; the actions never match.
**Fix:** The dedicated `lambda-microvms` boto3 client has **signing_name `lambda`**, so the IAM
actions are `lambda:CreateMicrovmImage`, `lambda:RunMicrovm`, `lambda:CreateMicrovmAuthToken`, … —
the **`lambda:` prefix**, NOT `lambda-microvms:`. Also grant `lambda:PassNetworkConnector` on the
AWS-managed connector ARNs (undocumented; surfaces only as a live `AccessDenied` when attaching the
INTERNET_EGRESS/HTTP_INGRESS connectors on the bake/run).

### On a MicroVM CREATE_FAILED bake, read the build log before re-baking

**Trigger:** A `CreateMicrovmImage` bake ends in `CREATE_FAILED` and you're tempted to tweak the
Dockerfile and retry.
**Symptom:** A blind guess-and-retry spiral — the bake runs your Dockerfile server-side AND then
boots the image to snapshot it, so a "clean `docker build`" can still fail in the **post-build
snapshot** phase (the platform starts your worker and waits for its readiness hook; if the worker
isn't serving that hook, the snapshot fails though the build was fine). Guessing can't tell the two
phases apart.
**Fix:** Pass a CloudWatch `logging` config to the bake, then **read the build log** (a read-only
`logs:FilterLogEvents` on `/aws/lambda/microvms/*` — `filter_log_events` needs no exact stream name
and is reliable right after the failure). One look tells you build-vs-snapshot and the exact failing
line. Only change something after reading the log.

### End a MicroVM run with SuspendMicrovm, not TerminateMicrovm (caller role has no Terminate)

**Trigger:** Writing the worker's end-of-run teardown, and reaching for `TerminateMicrovm` to fully
tear the VM down.
**Symptom:** The run completes but teardown fails with `AccessDenied` on `lambda:TerminateMicrovm`
(or `DeleteMicrovmImage`) — surprising, since the same role could `RunMicrovm` moments earlier.
**Fix:** The least-privilege caller role deliberately grants **Suspend/Resume but not
Terminate/Delete** — `SuspendMicrovm` is the pay-per-session pause and is all the run needs (a
suspended VM costs ~nothing; the `idlePolicy` also auto-suspends). Hard teardown happens out-of-band
on event/account reclaim. End every run with `SuspendMicrovm`; don't design a launcher around
`TerminateMicrovm` unless the role is explicitly granted it.

### Inside a MicroVM there is no shell profile — set the Bedrock model env in the worker

**Trigger:** The baked worker launches `sdharness run …` and relies on the model being configured,
the way it is in an interactive IDE terminal.
**Symptom:** The in-VM run stalls (retries indefinitely) or fails on `bedrock:InvokeModel`
AccessDenied, even though the execution role *can* invoke Bedrock — because it's scoped to specific
model/inference-profile ARNs and the run is calling a different (default) model.
**Fix:** A MicroVM has no interactive shell, so `.bashrc` is never sourced and `sdharness` falls back
to its **built-in default model**, which may not match the profiles the execution role allows. Pass
the model ids explicitly through the worker's environment (the Opus/Sonnet inference-profile ids the
exec role is scoped to), plus `CLAUDE_CODE_USE_BEDROCK=1` — don't rely on an ambient default.
