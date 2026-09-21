---
_fragment: collect
_of_phase: feedback
_contributes:
  - trace.json (anonymized migration trace)
  - feedback.json (survey URL, share-link state, trace_included flag)
---

# Feedback Phase: Collect

> Self-contained feedback-collection sub-file. Detects the IDE + plugin version,
> builds an anonymized trace, presents the survey link, and writes
> `feedback.json`. (Share-link generation is GATED OFF until the landing page ships.)

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 0: Detect IDE Type and Plugin Version

Detect IDE and plugin version for the survey URL (hidden fields — user never sees them).

- **Claude Code**: `CLAUDE_CODE` env var set → `ide = claude-code`
- **Cursor**: `CURSOR_TRACE_ID` env var set → `ide = cursor`
- **Kiro**: Kiro agent context → `ide = kiro`
- **Fallback**: `ide = unknown`

Read plugin version from nearest `plugin.json` → `version`. Fallback: `0.0.0`.
Sanitize both values to Pulse-safe chars: `[a-zA-Z0-9._~-]`.

Store as `$IDE_TYPE` and `$PLUGIN_VERSION`.

---

## Step 1: Build Trace

Build an anonymized trace from `$MIGRATION_DIR/` artifacts. Never include resource names,
file paths, account IDs, or secrets.

Trace fields (all anonymous):

- `skill`: `"azure-to-aws"`
- `phases_completed`: array of completed phase names from `.phase-status.json`
- `resource_type_counts`: object mapping `resource_type` → count (e.g. `{"web_app": 2}`)
- `compute_target`: from `preferences.design_constraints.compute_target.default`
- `ha_enabled`: from `preferences.global.high_availability`
- `specialist_gates_count`: count of entries in `azure-resource-inventory.json` specialist_gates[]
- `complexity_tier`: from `estimation-infra.json`

Write to `$MIGRATION_DIR/trace.json`.

---

## Step 2: Present Survey

Output to the user:

```
We'd love your feedback on this migration. It takes about 2 minutes and helps us improve
the tool for the startup community.

Your responses are anonymous — we never collect resource names, account IDs, or file paths.

Survey: https://pulse.aws/survey/azure-to-aws

[Press Enter to continue to Generate]
```

Wait for acknowledgement, then continue.

---

## Step 3: Share Link (GATED OFF)

> **GATED OFF** — the share landing page (`https://aws.amazon.com/startups/migrate/connect`)
> is not yet live. Do NOT generate or present a share link. This step is preserved here
> for when the page ships; removing the gate is the un-gating change.

---

## Step 4: Write feedback.json

```json
{
  "survey_presented": true,
  "share_link_generated": false,
  "share_link_gated": true,
  "trace_included": true,
  "ide": "<$IDE_TYPE>",
  "plugin_version": "<$PLUGIN_VERSION>"
}
```

Write to `$MIGRATION_DIR/feedback.json`. Pass to `feedback-assemble.md`.
