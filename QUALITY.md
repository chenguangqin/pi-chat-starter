# Quality Guidance

Directional standards the coding agent reads while writing code, and the Pilot
reads while reviewing. Seed it here and **grow it by hand** as you learn what "good"
means for your team; an automatic evaluator that appends after each run is a
documented extension (see docs/concepts/compound-engineering.md, Stage 4).

## Error handling

Prefer explicit error boundaries over silent failures. A user should always get
feedback when something goes wrong. Distinguish client errors from system failures
— don't catch everything the same way.

## Structure

Keep concerns in separate modules (e.g. UI → API → data). Validate inputs at
boundaries. Keep functions small enough to test in isolation.

## Testing

Write the validation *with* the code, not after. A milestone's validation should
be a command whose exit code / output is unambiguous evidence. "It works" is not
evidence; a passing command is.

## Configuration

Anything that varies across environments (region, endpoints, credentials) goes in
env vars or config, never hardcoded. Mark unavoidable prototype shortcuts with an
inline comment.

## Integration over units

Unit tests prove a component behaves; they do not prove the system works. The seams
between components — the wiring — are where AI-built systems silently half-work.
Prove the seams end-to-end in VERIFY (that is the whole point of the SD Loop's
integration report).
