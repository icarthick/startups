---
_phase: discover
_title: "Discover Azure Resources"
_init: true
_input: workspace
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/discover/discover-terraform.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - azure-resource-inventory.json
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
  - _assert: "at least one .tf file containing an azurerm_* resource exists in the workspace"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: azure-resource-inventory.json
    _on_failure: _halt_and_inform
  - _validate_json: azure-resource-inventory.json
    _on_failure: _halt_and_inform
  - _assert: "azure-resource-inventory.json has at least one resource entry, and metadata has discovery_timestamp and total_resources_discovered set"
    _on_failure: _halt_and_inform
  - _assert: "every resource in resources[] has resource_id, resource_type, and config fields"
    _on_failure: _halt_and_inform
  - _assert: "no forbidden clustering fields are present (cluster_id, creation_order_depth, edges, dependencies, must_migrate_together)"
    _on_failure: _halt_and_inform
  - _assert: "metadata.discovery_sources contains 'terraform'"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover Azure Resources

## Orientation

Inventory Azure resources declared in `azurerm` Terraform files into a single flat
`azure-resource-inventory.json` in `$MIGRATION_DIR/`. This phase is composed of one
FRAGMENT (the Terraform discoverer) plus one ASSEMBLER, declared in the frontmatter
`_fragments`/`_assemble` — the interpreter runs each fragment whose `_trigger` is true,
then the assembler.

This skill is **Terraform-only in v1**: it discovers from `.tf` files containing
`azurerm_*` resource blocks. ARM templates, Bicep files, and live Azure CLI discovery
are out of scope.

---

## Step 1: Run the Terraform Fragment

Load `references/phases/discover/discover-terraform.md` and follow it. It scans the
workspace for `.tf` files containing `azurerm_*` resources, extracts each resource's
configuration attributes, maps them to the inventory format, and produces the raw
resource list.

---

## Step 2: Assemble the Inventory

Load `references/phases/discover/discover-assemble.md` (the phase's assembler) and follow
it to assemble `azure-resource-inventory.json`, run the validation checklist, and update
`.phase-status.json`.

---

## Handoff

After the interpreter emits `HANDOFF_OK | phase=discover`, build the user-facing
completion message from the inventory contents:

- "Discovered X total resources across Y resource groups."
- If AKS clusters detected: "Detected N AKS cluster(s) (detect-only — specialist gate)."
- If Cosmos DB detected: "Detected N Cosmos DB account(s) (detect-only — specialist gate)."
- If Windows web apps detected: "Detected N Windows web app(s) (detect-only in v1)."

Format: "Discover phase complete. [artifact summaries] Next required step: Phase 2 —
Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or
Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as
`completed`."

---

## Error Handling

| Error Category                          | Behavior                                     |
| --------------------------------------- | -------------------------------------------- |
| Terraform parse error (malformed HCL)   | Log warning, skip malformed blocks, continue |
| No azurerm_* resources in scanned files | Fail precondition — unrecoverable            |
| Resource references unresolvable        | Record as `unresolved`, continue             |

---

## Scope Boundary

**This phase covers Azure Terraform Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons

**Your ONLY job: Inventory what exists in Azure Terraform files. Nothing else.**
