---
_assemble: feedback-assemble
_of_phase: feedback
_scope: >
  Validate feedback.json + trace.json against their schemas and confirm the
  flags are consistent with the files actually written + the trace is
  anonymized. ONLY this. Creates nothing, mutates nothing. Does NOT update
  .phase-status.json.
_reads: [feedback.json, trace.json]
_mutates: []
_produces: []
_postconditions:
  - _validate_json: feedback.json
  - _validate_schema: { file: feedback.json, schema: schemas/feedback.schema.json }
  - _assert: "feedback.json.survey_url starts with https://"
  - _assert: "CONSISTENCY: if feedback.json.trace_included == true then trace.json exists and validates against schemas/feedback-trace.schema.json; if false, no trace.json claim is made"
  - _assert: "CONSISTENCY: if feedback.json.share_link_presented == true then share_link_generated_at + share_checkpoint are non-null; if false they are null"
  - _assert: "ANONYMIZED: trace.json (if present) contains NO resource names, file paths, account IDs, or secrets — scan VALUES, not just keys: every leaf is a count, a known enum, or a numeric; discovery_sources holds only source-type enums (terraform/procfile/billing), never filenames; no value matches a known resource name or a *.tf/*.csv path"
_on_error:
  _halt_and_inform: { effect: "stop; surface diagnostic", status: retain_in_progress }
---

# Feedback Assembler

## Orientation

The mandatory feedback-phase ASSEMBLER (exactly one per phase, terminal), here a
validator: the collect fragment already wrote `feedback.json` (+ optionally
`trace.json`), so this unit creates nothing and mutates nothing — it owns the
artifact contract: both files validate against their schemas, the
`trace_included` / `share_link_presented` flags are CONSISTENT with what was
actually written, and the trace is ANONYMIZED. Its `_postconditions` ARE the
feedback handoff gate. It reads `feedback.json` + `trace.json`. Does NOT update
`.phase-status.json`.

## Step: validate_feedback

```meta
_reads: [feedback.json, trace.json]
```

Run every check in this unit's `_postconditions`. The CONSISTENCY checks
cross-reference the flags in `feedback.json` against the files on disk
(`trace_included` ⇔ a valid `trace.json`; `share_link_presented` ⇔ non-null
share metadata). The ANONYMIZED check re-reads `trace.json` and confirms it
carries only counts/types/enums — never resource names, file paths, account IDs,
or secrets (a leaked identifier is a fail-closed GATE_FAIL, since the trace is
telemetry).

Fail-closed (Golden Rule 1): on any failure emit
`GATE_FAIL | phase=feedback | field=<path> | reason=missing|invalid`, do NOT edit
the artifacts to force a pass, do NOT mark complete. Share-link absence is NOT a
failure (it is optional/non-blocking) — only an INCONSISTENT flag is.
