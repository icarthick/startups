---
_phase: discover
_title: "Discover Render Resources"
_init: true
_input: workspace
_fragments:
  - _id: render-yaml
    _trigger: { _always: true }
    _file: phases/discover/discover-render-yaml.md
  - _id: live
    _trigger: { _when: "$MIGRATION_DIR/live-capture/manifest.json exists" }
    _file: phases/discover/discover-live.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - render-resource-inventory.json
_advances_to: clarify
_interactive: false
_exec:
  _agent: rw
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: preferences.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "at least one Render source is available: a render.yaml file exists in the workspace, OR $MIGRATION_DIR/live-capture/manifest.json exists. Evaluating this check is where live capture is offered: if no render.yaml is found, offer live capture (consent-gated, read-only) as the primary source; fail this check only after the user declines live capture or capture cannot run"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: render-resource-inventory.json
    _on_failure: _halt_and_inform
  - _validate_json: render-resource-inventory.json
    _on_failure: _halt_and_inform
  - _assert: "render-resource-inventory.json has at least one resource entry, and metadata has discovery_timestamp and total_services_discovered set"
    _on_failure: _halt_and_inform
  - _assert: "every resource in resources[] has service_id, service_type, name, plan, and config fields"
    _on_failure: _halt_and_inform
  - _assert: "no forbidden clustering fields are present (cluster_id, creation_order_depth, edges, dependencies, must_migrate_together)"
    _on_failure: _halt_and_inform
  - _assert: "metadata.discovery_sources reflects which sub-discoveries actually produced data; if render.yaml was FOUND in the workspace, resources[] contains at least one render_yaml-sourced resource"
    _on_failure: _halt_and_inform
  - _assert: "if the live fragment ran ($MIGRATION_DIR/live-capture/manifest.json exists), resources[] contains at least one live-sourced resource, a live_metadata section is present, and 'live' appears in metadata.discovery_sources"
    _on_failure: _halt_and_inform
  - _assert: "no config var VALUES appear anywhere in the inventory — config entries carry key names only"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover Render Resources

## Orientation

Inventory what exists on Render into a single flat `render-resource-inventory.json`
in `$MIGRATION_DIR/`. This phase is composed of FRAGMENTS (independent discoverers)
plus one ASSEMBLER, declared in the frontmatter `_fragments`/`_assemble` — the
interpreter runs each fragment whose `_trigger` is true (loading its `_file` only
then), then the assembler. Read each unit file for its own contract; this phase
owns only lifecycle + the cross-cutting `_postconditions`.

The primary discovery source is `render.yaml` — Render's infrastructure-as-code
manifest. When a `render.yaml` is found in the workspace, the render-yaml fragment
parses all `services[]` entries and maps them to inventory resources. The live CLI
fragment (`render services list --output json`) is an optional cross-check, always
consent-gated.

### Live capture

Live discovery reads the user's Render account through their authenticated Render
CLI — read-only, consent-gated, key-names-only for environment variables. It is
split in two because the dispatched `rw` worker has no shell and cannot converse
with the user:

1. **Capture** (main-window pre-work) — runs in the MAIN window, after `_init` and
   before the phase's work is dispatched. It asks for consent, preflights the CLI
   (`render --version` or `render services list --output json` dry run), runs the
   read-only service list and info commands, and writes raw output to
   `$MIGRATION_DIR/live-capture/` plus a `manifest.json` index. It writes NO
   inventory entries.
2. **Parse** (`discover-live.md`, the `live` fragment) — runs in the worker with
   the other fragments. Its `_trigger` is the manifest's existence; it maps captures
   to inventory entries with `source: "live"`.

**Explicit ordering (cold start):** run `_init` state setup FIRST (create
`$MIGRATION_DIR`, write `.phase-status.json`), THEN evaluate the source
`_precondition` — offering and running live capture as part of that evaluation —
then dispatch the phase's work.

**When to offer capture:** while evaluating the source `_precondition`, scan the
workspace first (free). If NO `render.yaml` is found, offer live capture as the
primary source instead of failing the check. If `render.yaml` IS found, still offer
capture once as an optional live cross-check; a decline is fine and is not re-asked.
Never run capture without explicit consent.

**Source-of-truth rule (for the assembler):** when both render.yaml and live entries
exist, live is authoritative for current state (plans, quantities, regions); render.yaml
supplements structure. Disagreements are surfaced as drift, never silently resolved —
see `discover-assemble.md` § Merge & Drift Rules.

---

## Handoff

After the interpreter emits `HANDOFF_OK | phase=discover`, build the user-facing
completion message from the inventory contents:

- "Discovered X total services."
- If live discovery ran: "Live discovery captured N services via the Render CLI."
- If both live and render.yaml ran: "Drift check: N resources live but not in render.yaml, M in render.yaml but not live, K config conflicts (live values used)."

Format: "Discover phase complete. [artifact summaries] Next required step: Phase 2 — Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as `completed`."

---

## Error Handling

Non-fatal discovery errors and their handling (fatal source/gate failures are handled by `_preconditions`/`_postconditions` + `INTERPRETER.md` § `_on_error`):

| Error Category                                    | Behavior                                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| render.yaml parse error (malformed YAML)          | Log warning, skip malformed entries, continue                                                    |
| Unsupported service type in render.yaml           | Record warning per-service, mark as deferred, continue                                           |
| Live capture partially failed (some services 403) | Parse the `ok` captures, mark failed services `discovery_failed`, confidence `reduced`, continue |
| Live capture declined or CLI unavailable          | Skip the `live` fragment (no manifest → trigger never fires), continue with file-based sources   |

---

## Scope Boundary

**This phase covers Render Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists on Render. Nothing else.**
