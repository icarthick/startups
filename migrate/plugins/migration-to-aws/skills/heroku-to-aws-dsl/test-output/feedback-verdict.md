# Feedback Phase (DSL port) — VERDICT

**Change:** Ported Phase 6 (Feedback) — the TERMINAL, optional, LLM-driven phase
— from upstream `feedback.md`. It builds an anonymized `trace.json`, presents a
survey URL, optionally a shareable plan link, writes `feedback.json`, and marks
the migration COMPLETE. This is the LAST of the six phases.

Files authored:

- `phases/feedback.phase.md` — terminal phase: requires only discover, 1 collect
  fragment + validator assembler, `_advances_to: complete` (no next phase file).
- `phases/feedback/feedback-collect.md` — fragment: IDE/version detect, build
  the anonymized trace from whatever artifacts exist, survey URL, OPTIONAL
  share-link (shell-out encode, non-blocking), write trace.json + feedback.json.
- `phases/feedback/feedback-assemble.md` — validator: both files validate, the
  trace_included/share_link_presented flags are consistent with what was written,
  the trace is anonymized (value-scan).
- `knowledge/feedback/feedback-config.json` (survey/IDE/share/redaction config) +
  `schemas/feedback.schema.json` + `schemas/feedback-trace.schema.json`.

## The genuinely-hard leaf: share-link encoding

The share-link payload must be gzip + Base64URL encoded — real binary computation
a cold LLM cannot do by hand. Per the "must this be deterministic? → use a real
tool" principle, it is a documented SHELL-OUT
(`gzip -c | base64 | tr -d '\n' | tr '+/' '-_' | tr -d '='`), non-blocking (skip
on any failure). This is the feedback analogue of the design/estimate arithmetic
fork: deterministic structure stays DSL/prose, the one computational leaf is a
tool call.

## Cold-LLM test: PASS

Against a completed-pipeline fixture (all of discover..generate done), a cold LLM
executed feedback end-to-end: precondition passed, ide/version resolved to the
fallbacks (no env / no plugin.json), built the EXACT expected anonymized trace
(10 resources, type counts, 5 asked / 3 defaulted, 6 services, 8 tf files,
pricing cached, $199.49), the survey URL with sanitized fields, correctly SKIPPED
the share link, wrote a schema-valid feedback.json, and reached HANDOFF_OK ->
`complete`. It confirmed the terminal-phase handling is coherent (no phantom
`complete.phase.md`) and the trace carried no names/paths/ids. No closed-vocab
violation, no unclassifiable region.

## Findings (fixed)

1. **Share-link trigger was un-observable (REAL defect, FIXED).** The step gated
   on "invoked from a combined feedback+share flow" — invocation provenance the
   LLM cannot inspect, unlike every other (artifact/env/value) trigger in the
   DSL, leaving the share path effectively dead. Fixed: gate on an OBSERVABLE
   signal — `.phase-status.json.share_requested == true` OR
   `preferences.metadata.share_requested == true` (config `enabled_when` + the
   fragment `_when`); default skip when absent.
2. **`plugin_version` "nearest plugin.json" under-specified (REAL, FIXED).**
   "Nearest relative to what?" + three competing plugin.json variants. Pinned:
   search upward from the skill root; precedence .claude-plugin > .codex >
   .cursor; else 0.0.0.
3. **Trace anonymization rested on key-name forbidding, not value scanning
   (REAL, subtle, FIXED).** The schema's `not.anyOf` forbids three key names but
   would miss a filename leaked into a free string (e.g. `discovery_sources`).
   Tightened the trace step prose (discovery_sources = source-TYPE enum, not
   filenames; never copy an artifact object wholesale; every leaf is a
   count/enum/numeric) AND the assembler check to SCAN VALUES, not just keys.
4. **base64 portability (minor, FIXED).** Added `tr -d '\n'` so the encode is
   robust to GNU/BSD base64 line-wrapping.

## Net

Feedback is ported and cold-validated — the SIXTH and final phase. The terminal
phase (`_advances_to: complete`) and the shell-out encoding leaf both work; the
core trace/survey/feedback path is deterministic, and the one un-observable
trigger (the lone real defect) is now an observable artifact flag. **All six
phases of the heroku-to-aws DSL are now authored and cold-LLM validated** —
discovery, judgment (clarify), arithmetic (design/estimate), multi-artifact
generation, and terminal feedback. Remaining: the EKS cross-phase pass (design +
generate branches are stubs; estimate handling authored) and an optional CI
validator for the conformance checklists.
