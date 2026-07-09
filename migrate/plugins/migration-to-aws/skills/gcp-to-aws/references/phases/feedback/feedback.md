---
_phase: feedback
_title: "Feedback (Optional)"
_kind: checkpoint
_requires_phase: discover
_input: "**/.phase-status.json"
_trigger: { _when: "the user opts in to providing feedback at a feedback checkpoint (offered after Discover and after Estimate)" }
_fragments:
  - _id: trace
    _trigger: { _always: true }
    _file: phases/feedback/feedback-trace.md
_assemble:
  _file: phases/feedback/feedback-assemble.md
_produces:
  - feedback.json
  - trace.json
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: feedback.json
    _on_failure: _warn_and_skip
  - _validate_json: feedback.json
    _on_failure: _warn_and_skip
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
---

# Feedback (Optional Checkpoint)

Builds an anonymized usage trace and directs the user to the Pulse survey form.

**Execute ALL steps in order. Do not skip or deviate.**

This is an **off-backbone checkpoint** (`_kind: checkpoint`), entered by its phase-level
`_trigger` when the user opts in. Per `INTERPRETER.md` § Backbone vs checkpoint it
returns control instead of advancing (no `_advances_to`). WHERE it is offered (after
Discover and after Estimate) is orchestration prose in SKILL.md, not part of this
phase's contract. Marking `phases.feedback` `"completed"` means the checkpoint was
**resolved** (offered and dealt with), not that the user participated — participation
is signalled by the presence of `feedback.json`.

## Prerequisites

Read `$MIGRATION_DIR/.phase-status.json`. Verify `phases.discover == "completed"`. If not: **STOP**. Output: "Feedback requires at least the Discover phase to be completed."

## Step 0: Detect IDE Type and Plugin Version

Detect the IDE type and plugin version for the survey URL. These are passed as hidden fields — the user never sees or enters them.

### IDE Detection

Determine which IDE is running:

- **Claude Code**: Check if the environment indicates Claude Code (e.g., the `CLAUDE_CODE` environment variable is set, or the skill was invoked via `/skill` or Claude Code CLI). Set `ide` to `claude-code`.
- **Cursor**: Check if the environment indicates Cursor (e.g., the `CURSOR_TRACE_ID` environment variable is set, or the editor context is Cursor). Set `ide` to `cursor`.
- **Fallback**: If detection fails, set `ide` to `unknown`.

### Plugin Version Detection

Read the plugin version from the plugin manifest:

- **Claude Code**: Read `.claude-plugin/plugin.json` → `version` field (relative to the plugin install root).
- **Cursor**: Read `.cursor-plugin/plugin.json` → `version` field (relative to the plugin install root).
- **Fallback**: If the manifest cannot be read, set `version` to `0.0.0`.

### Sanitization

Values must use only Pulse-safe characters: letters, numbers, dots (`.`), tildes (`~`), hyphens (`-`), and underscores (`_`). Strip or replace any other characters.

Store the detected values as `$IDE_TYPE` and `$PLUGIN_VERSION` for use in Step 2.

## Step 1: Build Trace

Load `references/phases/feedback/feedback-trace.md` and execute it. This produces `$MIGRATION_DIR/trace.json`.

If trace building fails: log the error, set `trace_included` to `false`, and skip to Step 3.

## Step 2: Show Trace and Provide Instructions

Read `$MIGRATION_DIR/trace.json` and display it pretty-printed so the user can see exactly what data is included:

```
--- Anonymized Trace (what will be shared) ---

<pretty-printed trace.json>

--- End Trace ---

This trace contains only aggregate counts, enum values, and timing data.
No resource names, file paths, account IDs, or secrets are included.
```

Then output the single-line minified version for copy-paste:

```
--- Copy the line below and paste it into the "Migration trace (optional)" field ---

<trace.json as single-line minified JSON — no newlines, no extra whitespace>

--- End ---
```

Then provide the survey link with IDE and version as hidden field query parameters:

```
Open the feedback form in your browser:
https://pulse.amazon/survey/MY0ZY7UA?ide=$IDE_TYPE&version=$PLUGIN_VERSION

Answer the 5 quick questions in the form, then paste the trace line above
into the "Migration trace (optional)" field and submit.
```

Replace `$IDE_TYPE` and `$PLUGIN_VERSION` with the actual values detected in Step 0. Example: `https://pulse.amazon/survey/MY0ZY7UA?ide=claude-code&version=1.0.0`

## Step 3: Assemble and Complete

Load `references/phases/feedback/feedback-assemble.md` (the phase's assembler) and
follow it to write `feedback.json`, enforce the output gate, and resolve the
checkpoint. It owns the artifact-level contract for this phase.
