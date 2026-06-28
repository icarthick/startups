---
# ============================================================================
# feedback.phase.md — Phase 6 (Feedback, TERMINAL).
# THIN phase. The LLM-driven, optional, terminal phase: build an anonymized
# trace, present a survey URL, optionally a shareable plan link, write
# feedback.json, and mark the migration COMPLETE (_advances_to: complete — no
# next phase to load).
#
# Single responsibility (collect feedback) -> ONE fragment (feedback-collect,
# writes trace.json + feedback.json + optional share link) + a validator
# assembler. Mostly judgment/telemetry; the DSL provides the lifecycle + the two
# output contracts. The ONE non-LLM-deterministic leaf is the share-link encode
# (gzip + Base64URL) \u2014 done by SHELL-OUT (documented tool-use), non-blocking.
#
# Requires only DISCOVER (feedback can run on a partial pipeline); each trace
# section is included only if its artifact exists.
# ============================================================================
_phase: feedback
_title: "Feedback (Optional)"
_requires_phase: discover
_scope: >
  Collect anonymized feedback and (optionally) a shareable plan link, then mark
  the migration complete. ONLY this. No re-design, no re-estimate, no
  regeneration, no new clarify questions. The trace MUST be anonymized (no
  resource names, file paths, account IDs, or secrets).

_input:
  - "**/.phase-status.json"

_knowledge:
  - { file: knowledge/feedback/feedback-config.json }

_preconditions:
  - _check_phase_completed: discover
    _on_failure:
      _halt_and_inform: >
        Feedback requires at least the discover phase to be completed.

_fragments:
  - _id: collect
    _trigger: { _always: true }
    _file: phases/feedback/feedback-collect.md

_assemble:
  _file: phases/feedback/feedback-assemble.md

_postconditions:
  - _check_file_exists: feedback.json
  - _assert: "if feedback.json.trace_included == true -> trace.json exists"

_produces: [feedback.json, trace.json]
_advances_to: complete
_forbids_files:
  - "*.txt"
  - feedback-summary.md

_on_error:
  _warn_and_skip:   { effect: "record warning; skip the optional item (e.g. trace or share link); continue", status: continue }
  _halt_and_inform: { effect: "stop; surface diagnostic",                                                     status: retain_in_progress }
---

# Feedback (Optional)

## Orientation

The terminal, optional, LLM-driven phase: build an anonymized `trace.json`,
present the survey URL, optionally produce a shareable plan link, write
`feedback.json`, and mark the migration COMPLETE. The work is ONE FRAGMENT + one
ASSEMBLER:

1. **collect** fragment (`phases/feedback/feedback-collect.md`) — detect IDE +
   plugin version (from env, else fallback), build the anonymized trace from
   whatever artifacts exist, present the survey URL, OPTIONALLY build the
   share-link payload (encoded by shelling out to `gzip | base64url` —
   non-blocking, skip on any failure), and write `trace.json` + `feedback.json`.
2. **feedback-assemble** (`phases/feedback/feedback-assemble.md`) — validator:
   `feedback.json` validates + its `trace_included`/`share_link_presented` flags
   are consistent with the files actually written, and `trace.json` (if present)
   is anonymized (no names/ids/paths/secrets).

Config (survey URL, IDE map, share-link rules, redaction patterns) is
`knowledge/feedback/feedback-config.json`; output SHAPES are
`schemas/feedback.schema.json` + `schemas/feedback-trace.schema.json`. This is
the LAST phase: `_advances_to: complete` \u2014 there is NO next phase file to load.
After the assembler validates, the phase emits
`HANDOFF_OK | phase=feedback | artifacts=feedback.json,trace.json`, sets
`phases.feedback="completed"`, `current_phase="complete"`, and tells the user the
migration planning is finished.
