# Agent Instructions

You are a coding agent running inside a harness. Your workspace is a project
directory; all files you create stay here. These are the non-negotiable rules.

> This file, `QUALITY.md`, and `LESSONS.md` are staged into your workspace every
> run. They are the harness's accumulated knowledge — read them before you start.
> This is *the compounding cycle*: each run's lessons make the next run better.

## What you're building

Your output is meant to be inherited by a human engineer who was not part of this
run. They must understand it, modify it, and ship it without talking to you. Every
design doc and every comment on a non-obvious decision exists for that person.

## Workflow

You are following a structured lifecycle driven by the method (see the system
prompt). It defines phases with gates between them. Follow it precisely. The
harness — not you — decides when a phase is complete, by checking that the phase's
artifacts exist. Produce the artifacts; don't try to self-advance.

## Knowledge files (read them)

- **LESSONS.md** — Trigger / Symptom / Fix entries for known traps. Check your work
  against these before presenting at a gate.
- **QUALITY.md** — Directional quality standards. Follow unless the project conflicts.
- **CLAUDE.md** — This file. Non-negotiable rules.

## Code quality

- Write real, working code. No placeholders, no TODOs, no "implement later" stubs.
- Prefer simple, readable implementations over clever abstractions.
- Run the validation after writing code. Fix failures before moving on.
- Resolve type/lint issues at the root — don't suppress with `# type: ignore` / `noqa` / `@ts-ignore`.
- Keep layers separated; validate at boundaries; keep environment-specific values in config.
- Build real integrations. If a feature needs an API call or a database, wire it up for real.
- Surface constraints early — present blockers at the next gate with options rather than
  working around them silently.
- Mark prototype-only shortcuts with an inline comment so the human knows what to change.

## Gate discipline

- A milestone box (`- [x]`) flips only when its stated validation actually passed — and you
  logged the outcome the same turn. The Pilot will NO_GO an unbacked checkbox.
- Record new constraints you discover in `progress.md` (Patterns) and `goal.md` (Open Questions).
