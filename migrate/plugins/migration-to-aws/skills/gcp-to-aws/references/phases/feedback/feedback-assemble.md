---
_assemble: assemble-feedback
_of_phase: feedback
_reads:
  - trace (fragment contribution)
_produces:
  - feedback.json
---

# Feedback — Assemble & Complete

> **Assembler unit.** Runs after the `trace` fragment (`feedback-trace.md`) has built
> `trace.json`. It writes the `feedback.json` record and resolves the checkpoint. See
> `feedback.md` for how this unit is composed into the phase.

**Execute ALL steps in order. Do not skip or deviate.**

## Step 1: Write feedback.json

Write `$MIGRATION_DIR/feedback.json`:

```json
{
  "timestamp": "<ISO 8601>",
  "survey_url": "https://pulse.amazon/survey/MY0ZY7UA?ide=$IDE_TYPE&version=$PLUGIN_VERSION",
  "phases_completed_at_feedback": ["<list of completed phases>"],
  "trace_included": true
}
```

If trace building failed: set `"trace_included": false`.

## Step 2: Output gate

- `feedback.json` must exist.
- If `trace_included` is true, `trace.json` must exist.

If the output gate fails: STOP and output: "Feedback outputs are incomplete. Fix
feedback artifacts before completion."

## Step 3: Resolve the checkpoint

This is a checkpoint (`INTERPRETER.md` § Backbone vs checkpoint). Marking
`phases.feedback` `"completed"` means the checkpoint was **resolved** — offered and
dealt with — not that the user participated. Update `.phase-status.json` with
`phases.feedback: "completed"` in the same turn as the message below.

Output to user: "Thank you for helping improve this tool."

After feedback completes, **return control** to the interpreter loop (a checkpoint does
not advance a backbone edge). The calling checkpoint site (after Discover or after
Estimate — see SKILL.md) determines whether the backbone continues or the migration
ends.
