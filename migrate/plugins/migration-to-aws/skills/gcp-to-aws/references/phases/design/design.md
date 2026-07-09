---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - preferences.json
  - gcp-resource-inventory.json
  - gcp-resource-clusters.json
  - billing-profile.json
  - ai-workload-profile.json
_fragments:
  - _id: design-infra
    _trigger: { _when: "gcp-resource-inventory.json AND gcp-resource-clusters.json both exist (IaC discovery ran)" }
    _file: phases/design/design-infra.md
  - _id: design-billing
    _trigger: { _when: "billing-profile.json exists AND gcp-resource-inventory.json does NOT exist (billing-only fallback)" }
    _file: phases/design/design-billing.md
  - _id: design-ai
    _trigger: { _when: "ai-workload-profile.json exists" }
    _file: phases/design/design-ai.md
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - { file: aws-design.json, _when: "IaC route active (gcp-resource-inventory.json exists)" }
  - { file: aws-design-billing.json, _when: "billing-only route active (billing-profile.json exists, no gcp-resource-inventory.json)" }
  - { file: aws-design-ai.json, _when: "AI route active (ai-workload-profile.json exists)" }
_advances_to: estimate
_re_entry_guard:
  _stale_if_completed: estimate
  _stale_artifact: estimation-infra.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: preferences.json
    _on_failure: _unrecoverable
  - _validate_json: preferences.json
    _on_failure: _unrecoverable
  - _assert: "at least one discovery artifact exists (gcp-resource-inventory.json, billing-profile.json, or ai-workload-profile.json); if none, Design cannot run"
    _on_failure: _unrecoverable
_postconditions:
  - _assert: "at least one design route was active and produced its artifact: IaC route -> aws-design.json; billing-only route -> aws-design-billing.json; AI route -> aws-design-ai.json. If no route is active, the phase must not complete"
    _on_failure: _halt_and_inform
  - _assert: "every active route produced valid JSON: for each of aws-design.json / aws-design-billing.json / aws-design-ai.json that a triggered route was responsible for, the file exists and parses"
    _on_failure: _halt_and_inform
  - _assert: "if aws-design.json exists: it has phase == 'design' and a valid timestamp; services[] is present (empty only if all resources deferred); every services[] entry has service_id, source_resource_id, aws_service, confidence, aws_config; metadata.total_services matches services[].length"
    _on_failure: _halt_and_inform
  - _assert: "if BigQuery was flagged in discovery, the corresponding resources appear as 'Deferred — specialist engagement' in the design output (no Athena/Redshift/Glue/EMR recommendation)"
    _on_failure: _halt_and_inform
  - _assert: "design-infra and design-billing never both produced an artifact in the same run (billing-only is the fallback when no IaC exists)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md
  - estimation-infra.json
  - estimation-ai.json
  - estimation-billing.json
---

# Phase 3: Design AWS Architecture (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(clarify completed, single active phase, preferences present + valid, ≥1 discovery
artifact), the `.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion
gate are owned by the interpreter and this phase's frontmatter. The prose below is the
design **routing procedure**.

Design has **three routes**, selected by which discovery artifacts exist. Each route
is a fragment fired by its `_when` trigger, and each writes its own conditional
artifact (see `_produces`). Multiple routes can run in one migration (infra + AI is a
common hybrid); infra and billing-only are mutually exclusive.

## Step 1: Run the Active Design Routes

Run each route whose `_when` trigger holds (the interpreter loads the fragment only
when its trigger fires):

- **Infrastructure** (`design-infra.md`) — when `gcp-resource-inventory.json` and
  `gcp-resource-clusters.json` exist. Writes `aws-design.json`.
- **Billing-only** (`design-billing.md`) — when `billing-profile.json` exists and
  `gcp-resource-inventory.json` does NOT (fallback path). Writes `aws-design-billing.json`.
- **AI** (`design-ai.md`) — when `ai-workload-profile.json` exists. Writes
  `aws-design-ai.json`. Runs independently of the infra/billing route (no shared
  state); run it after the infra/billing design completes.

## Step 2: Assemble and Validate

Load `references/phases/design/design-assemble.md` (the phase's assembler) and follow
it to enforce the route output gates (≥1 active route produced its artifact; infra
XOR billing) and own the phase's artifact-level contract.

## Reference Files

Sub-design files may reference rubrics in `design-refs/`:

- `design-refs/index.md` — GCP type → rubric file lookup
- `design-refs/fast-path.md` — Direct (table) mappings vs rubric path; **User-facing vocabulary** for presenting `confidence` to users (**Standard pairing** / **Tailored to your setup** / **Estimated from billing only**)
- `design-refs/compute.md` — Compute service rubric
- `design-refs/database.md` — Database service rubric
- `design-refs/storage.md` — Storage service rubric
- `design-refs/networking.md` — Networking service rubric
- `design-refs/messaging.md` — Messaging service rubric
- `design-refs/ai.md` — AI/ML service rubric

## Scope Boundary

**This phase covers architecture mapping ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Cost calculations or pricing estimates
- Execution timelines or migration schedules
- Terraform or IaC code generation
- Risk assessments or rollback procedures
- Team staffing or resource allocation

**Your ONLY job: Map GCP resources to AWS services. Nothing else.**
