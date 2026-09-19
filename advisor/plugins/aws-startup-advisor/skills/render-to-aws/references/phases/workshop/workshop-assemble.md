---
_assemble: assemble-workshop
_of_phase: workshop
_reads:
  - scenarios/index.json
_produces:
  - scenarios/index.json (finalized)
---

# Workshop Phase: Assembler (Exit)

> Resolves the workshop sidebar. Ensures the working tree matches the active scenario,
> updates `phases.workshop` to `"completed"`, and hands back control to the
> Estimate→Generate flow.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Verify Active Scenario Files

Read `scenarios/index.json.active_scenario_id`. Ensure the working tree files
(`preferences.json`, `aws-design.json`, `estimation-infra.json`) match that scenario's
snapshot files. If they don't match:

1. Restore the active scenario's files from `scenarios/<active_scenario_id>.*` to the working tree.
2. Update `preferences.workshop.active_scenario_id` to the active scenario.

---

## Step 2: Mark Workshop Completed

Set `preferences.workshop.active = false`.
Update `phases.workshop` to `"completed"` in `.phase-status.json`.

---

## Step 3: Advance to Generate

Set `current_phase` to `"generate"` in `.phase-status.json` (this is the deferred advance
from `estimate-assemble.md` § Step 8 — the workshop gate has now resolved).

Output to user: "Workshop complete. Active scenario: [label]. Proceeding to Phase 5: Generate Migration Artifacts."
