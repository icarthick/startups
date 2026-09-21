---
_phase: preflight
_title: "Preflight Readiness Check (Optional)"
_kind: sidebar
_requires_phase: estimate
_trigger:
  {
    _when: "user opts in post-Estimate preflight offer [A], or says preflight / readiness check / check quotas / check region availability",
  }
_input:
  - aws-design.json
  - preferences.json
_fragments:
  - _id: check
    _trigger: { _always: true }
    _file: phases/preflight/preflight-check.md
_assemble:
  _file: phases/preflight/preflight-assemble.md
_produces:
  - preflight-report.json
_interactive: true
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, preferences.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: preflight-report.json
    _on_failure: _warn_and_skip
  - _validate_json: preflight-report.json
    _on_failure: _warn_and_skip
  - _assert: "preflight-report.json has a status field and its value is one of {pass, warn, blocked}"
    _on_failure: _warn_and_skip
  - _assert: "preflight-report.json has a blockers array and a quota_items array"
    _on_failure: _warn_and_skip
---

# Phase: Preflight Readiness Check (Sidebar)

> **Sidebar** (`_kind: sidebar`), not a backbone step — same class as
> `workshop` and `feedback`. Entered only when its `_trigger` fires; has **no**
> `_advances_to`; never becomes `current_phase`. Returns control to the
> Estimate→Generate flow after the check resolves or is declined.

**Execute ALL steps in order. Do not skip or deviate.**

## Entry

1. Preconditions above must pass. Do **not** re-run Estimate or Discover.
2. Set `phases.preflight` to `"in_progress"` (do not change `current_phase` —
   sidebars never own it).

## Work

1. Load `references/phases/preflight/preflight-check.md` and follow it.
   It iterates the proposed AWS services from `aws-design.json`, queries the
   AWS documentation-lookup capability for regional availability and default
   quota coverage, and accumulates blockers and quota-increase items.
2. Load `references/phases/preflight/preflight-assemble.md` (the phase's
   assembler) and follow it to write `preflight-report.json` and mark the
   sidebar resolved.

## Hard rules

| Rule                         | Behavior                                                                                                  |
| ---------------------------- | --------------------------------------------------------------------------------------------------------- |
| Inventory frozen             | Never write `heroku-resource-inventory.json` or `capture/`                                                |
| No Generate in sidebar       | Sidebar does not advance `current_phase`; estimate-assemble owns that                                     |
| Do not hardcode quota values | All quota thresholds must be sourced at runtime via AWS documentation-lookup                              |
| Blockers are non-blocking    | A `blocked` status surfaces items for the user to act on; Generate still proceeds after user acknowledges |

## Decline without entering

When the preflight offer **[B] Skip, proceed to Generate** is chosen, do not
enter this phase's fragments — mark `phases.preflight` `"completed"` (resolved/declined per
sidebar semantics in `INTERPRETER.md`), then advance `current_phase` → `"generate"`
per the preflight offer resolution path in `estimate-assemble.md`.
