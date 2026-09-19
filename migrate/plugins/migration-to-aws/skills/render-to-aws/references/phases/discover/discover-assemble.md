---
_assemble: assemble-inventory
_of_phase: discover
_reads:
  - render-yaml fragment contribution (render_yaml-sourced entries)
  - live fragment contribution (live-sourced entries, if fragment ran)
_produces:
  - render-resource-inventory.json
---

# Discover — Assemble and Write render-resource-inventory.json

> **Assembler unit.** Runs after all triggered fragments have completed. It merges
> render.yaml-sourced and live-sourced resource entries, resolves conflicts, and writes
> the final `render-resource-inventory.json`. All user communication is via output
> messages only (no report or log files).

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Collect Fragment Contributions

Collect all resource entries from the fragments that ran:

- From the render.yaml fragment: entries with `source: "render_yaml"`
- From the live fragment (if ran): entries with `source: "live"`

---

## Step 2: Merge and Deduplicate

### Merge Rules

When both sources provide entries for the same service (matched by `name` + `service_type`):

1. **Live is authoritative for current state**: plan, num_instances, region, config values
2. **render.yaml supplements structure**: env_vars_keys, health_check_path, schedule
3. **Combined entry**: `source: "render_yaml+live"`, merging config from both sources
4. **Disagreements are surfaced as drift** — never silently resolve conflicting plan/type:
   - Record in `metadata.drift_notes[]`: e.g., `"service acme-api: render.yaml plan=standard, live plan=pro (live used)"`

### Keys-Only Rule (enforced here)

Scan every `config.env_vars_keys[]` entry. If any entry looks like a value (contains `=`, is longer than 64 chars, or matches a known secret pattern), remove it and record a `config_redaction_warning`. **Never carry values.**

---

## Step 3: Compute Metadata

```json
{
  "metadata": {
    "discovery_timestamp": "<ISO timestamp>",
    "total_services_discovered": N,
    "discovery_sources": ["render_yaml"],
    "confidence": "high|reduced",
    "drift_notes": []
  }
}
```

Set `discovery_sources` to the set of sources that produced at least one entry.
Set `confidence` to `"reduced"` if:

- live capture was attempted but partially failed, OR
- any drift was detected between render.yaml and live

---

## Step 4: Write render-resource-inventory.json

Write `$MIGRATION_DIR/render-resource-inventory.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "render-to-aws",
  "metadata": {
    "discovery_timestamp": "<ISO 8601>",
    "total_services_discovered": N,
    "discovery_sources": ["render_yaml"],
    "confidence": "high",
    "drift_notes": []
  },
  "services": [
    {
      "service_id": "render:<name>:<type>",
      "service_type": "web_service|background_worker|cron_job|postgres|key_value|static_site|private_service",
      "name": "<service name>",
      "plan": "<plan tier>",
      "region": "<render region>",
      "source": "render_yaml|live|render_yaml+live",
      "config": { }
    }
  ],
  "live_metadata": null
}
```

Include `live_metadata` only when the live fragment ran. Omit the key entirely when only render.yaml was used.

**Forbidden:** No clustering fields (`cluster_id`, `creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`). Resources are a flat list.

---

## Step 5: Completion Gate

Re-read `render-resource-inventory.json`. Verify:

- Valid JSON
- At least one service entry
- `metadata.discovery_timestamp` is set
- No config var VALUES appear (keys only)
- No clustering fields present
- If live fragment ran: `live_metadata` is present and `"live"` is in `discovery_sources`

On success: emit `HANDOFF_OK | phase=discover`.
On failure: emit `GATE_FAIL` with the specific failure reason.
