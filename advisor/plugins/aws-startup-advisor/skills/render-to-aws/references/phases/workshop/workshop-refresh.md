---
_fragment: refresh
_of_phase: workshop
_trigger: { _when: "user chose Apply & reprice" }
_contributes:
  - new scenario snapshot (scenarios/scenario-NNN.* files)
  - updated scenarios/index.json
---

# Workshop Phase: Refresh (Inner Design + Estimate)

> Applies the patched preferences, runs inner Design + inner Estimate (artifact rewrite
> only — no user interaction, no new discovery), and snapshots the result as a new scenario.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Validate Inventory Fingerprint

Compute SHA-256 of `$MIGRATION_DIR/render-resource-inventory.json`.
Compare against `scenarios/index.json.inventory_fingerprint`.
If different: STOP with error "Inventory changed since workshop started. Re-run Discover to refresh."

---

## Step 2: Apply Patched Preferences

Write the patched preferences (from `workshop-sheet.md` § Step 3 knob changes) to
`$MIGRATION_DIR/preferences.json`. This is the "active" preferences file.

Patch `preferences.workshop.last_sheet_at` to the current timestamp.

---

## Step 3: Inner Design Run (Artifact Rewrite Only)

Re-run the design mapping engine from `design-mapping.md` with the patched preferences.
Write the result back to `$MIGRATION_DIR/aws-design.json`.

This is a **silent rewrite** — no user-facing output, no phase status updates.
The design mapping engine must respect the new `compute_target.default` and `cpu_architecture`.

---

## Step 4: Inner Estimate Run (Artifact Rewrite Only)

Re-run the cost engine from `estimate-cost-engine.md` with the patched preferences and new design.
Write the result back to `$MIGRATION_DIR/estimation-infra.json`.

This is a **silent rewrite** — no user-facing output.

---

## Step 5: Snapshot as New Scenario

Determine next scenario number: count existing scenarios in `scenarios/index.json` → N+1.
Set `scenario_id = "scenario-{NNN}"` (zero-padded to 3 digits).

Check max_scenarios gate (max 5):

- If `len(scenarios) >= 5` (not counting baseline):
  - Identify the oldest non-baseline scenario.
  - Warn: "Maximum scenarios reached. Evicting [label] (scenario-NNN) to make room."
  - Delete `scenarios/scenario-NNN.json`, `scenarios/scenario-NNN.preferences.json`, etc.
  - Remove the entry from `index.json.scenarios[]`.

Copy snapshots:

- `preferences.json` → `scenarios/scenario-NNN.preferences.json`
- `aws-design.json` → `scenarios/scenario-NNN.aws-design.json`
- `estimation-infra.json` → `scenarios/scenario-NNN.estimation-infra.json`

Write manifest `scenarios/scenario-NNN.json`:

```json
{
  "scenario_id": "scenario-NNN",
  "label": "<user-provided label or auto from knob changes>",
  "created_at": "<ISO timestamp>",
  "source": "workshop",
  "preferences_subset": { <changed dot-paths from sheet> },
  "preferences_fingerprint": "<sha256 of preferences.json>",
  "aws_design_fingerprint": "<sha256 of aws-design.json>",
  "estimation_summary": {
    "aws_monthly_premium": <from estimation-infra.json>,
    "aws_monthly_balanced": <from estimation-infra.json>,
    "aws_monthly_optimized": <from estimation-infra.json>,
    "complexity_tier": "<from estimation-infra.json>",
    "pricing_source": "<from estimation-infra.json>",
    "region_note": "<if region changed and MCP unavailable, note 'rates are us-east-1-based'>"
  },
  "paths": {
    "preferences": "scenarios/scenario-NNN.preferences.json",
    "aws_design": "scenarios/scenario-NNN.aws-design.json",
    "estimation_infra": "scenarios/scenario-NNN.estimation-infra.json"
  }
}
```

Update `scenarios/index.json`:

- Add the new scenario to `scenarios[]`
- Set `active_scenario_id = "scenario-NNN"`

Update `preferences.workshop.active_scenario_id = "scenario-NNN"`.

After refresh completes, automatically load `workshop-compare.md` to show the comparison table.
