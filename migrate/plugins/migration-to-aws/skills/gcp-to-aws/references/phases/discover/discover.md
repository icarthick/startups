---
_phase: discover
_title: "Discover GCP Resources"
_init: true
_input: workspace
_fragments:
  - _id: iac
    _trigger: { _glob: "**/*.tf" }
    _file: phases/discover/discover-iac.md
  - _id: app-code
    _trigger: { _when: "source code or dependency manifests exist in the workspace (**/*.py, **/*.js, **/*.ts, requirements.txt, package.json, go.mod, pom.xml, etc.)" }
    _file: phases/discover/discover-app-code.md
  - _id: billing
    _trigger: { _glob: "**/*{billing,cost,usage}*.{csv,json}" }
    _file: phases/discover/discover-billing.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - { file: gcp-resource-inventory.json, _when: "Terraform/IaC files were found (discover-iac ran)" }
  - { file: gcp-resource-clusters.json, _when: "Terraform/IaC files were found (discover-iac ran)" }
  - { file: ai-workload-profile.json, _when: "AI confidence >= 70% in app code, and/or Vertex-strong IaC inference" }
  - { file: billing-profile.json, _when: "billing/cost/usage export files were found" }
  - migration-preview.json
_advances_to: clarify
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: preferences.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "at least one GCP source is present in the workspace: a .tf/.tfvars/.tfstate file, application source code, or a billing/cost/usage export"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: migration-preview.json
    _on_failure: _halt_and_inform
  - _validate_json: migration-preview.json
    _on_failure: _halt_and_inform
  - _assert: "at least one discovery artifact was produced (gcp-resource-inventory.json, ai-workload-profile.json, or billing-profile.json); if none, the phase must not complete"
    _on_failure: _halt_and_inform
  - _assert: "every triggered discovery route produced its required artifact(s): if discover-iac ran then gcp-resource-inventory.json and gcp-resource-clusters.json exist; if full discover-billing ran or lightweight billing extraction ran then billing-profile.json exists; if app-code discovery continued past its confidence gate then ai-workload-profile.json exists"
    _on_failure: _halt_and_inform
  - _assert: "migration-preview.json has complexity_signal set"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - EXECUTION_REPORT.txt
  - discovery-log.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover GCP Resources

Lightweight orchestrator that delegates to domain-specific discoverers. Each sub-discovery file is self-contained — it scans for its own input, processes what it finds, and exits cleanly if nothing is relevant.
**Execute ALL steps in order. Do not skip or deviate.**

This skill is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(single active phase, at least one source present), the `.phase-status.json` write,
and the `HANDOFF_OK`/`GATE_FAIL` completion gate are all owned by the interpreter and
this phase's frontmatter — the prose below is the discovery **procedure** only. This
phase carries `_init: true`; per `INTERPRETER.md` § `_init` it bootstraps migration
state (resume-vs-fresh, `$MIGRATION_DIR`, `.gitignore`, initial `.phase-status.json`)
before the fragments run.

## Sub-Discovery Files (fragments)

The discovery work is split across three independent fragments, each fired by its
`_trigger` (see this phase's `_fragments` frontmatter) and each contributing to the
phase's artifacts. Multiple can run in one invocation — they are not mutually
exclusive.

- **`discover-iac.md`** (`_glob: **/*.tf`) → `gcp-resource-inventory.json` +
  `gcp-resource-clusters.json`; may also contribute `ai-workload-profile.json` when
  the Terraform is **Vertex-strong** (its Step 7d).
- **`discover-app-code.md`** (source code / dependency manifests present) →
  contributes `ai-workload-profile.json` when AI confidence ≥ 70%.
- **`discover-billing.md`** (`_glob: **/*{billing,cost,usage}*.{csv,json}`) →
  `billing-profile.json`. It self-selects full vs lightweight extraction based on
  whether Terraform is also present (see that fragment).

The `discover-assemble.md` assembler is the single creator of the two cross-cutting
artifacts: the **merged** `ai-workload-profile.json` (reconciling the app-code and
IaC-Vertex contributions) and the derived `migration-preview.json`.

## Execution

The interpreter loop (`INTERPRETER.md`) drives this phase: it establishes migration
state (this phase's `_init: true` — see § `_init`), runs the `_preconditions` entry
gate, fires each fragment on its `_trigger`, runs the assembler, then runs the
`_postconditions` completion gate and advances on `HANDOFF_OK` per `_advances_to`. None
of that scaffolding is restated here — the frontmatter and `INTERPRETER.md` own it.
The prose below is only the fragment-selection detail specific to GCP discovery.

### Fragment selection detail

The fragment triggers in frontmatter are the source of truth; this expands the input
patterns each one scans for:

- **Terraform / IaC** (`discover-iac.md`): `**/*.tf`, `**/*.tfvars`, `**/*.tfstate`,
  `**/.terraform.lock.hcl`.
- **Source code / dependency manifests** (`discover-app-code.md`): `**/*.py`,
  `**/*.js`, `**/*.ts`, `**/*.jsx`, `**/*.tsx`, `**/*.go`, `**/*.java`, `**/*.scala`,
  `**/*.kt`, `**/*.rs`, `**/requirements.txt`, `**/setup.py`, `**/pyproject.toml`,
  `**/Pipfile`, `**/package.json`, `**/go.mod`, `**/pom.xml`, `**/build.gradle`.
- **Billing data** (`discover-billing.md`): `**/*billing*.{csv,json}`,
  `**/*cost*.{csv,json}`, `**/*usage*.{csv,json}`. When Terraform was **also** found,
  the billing fragment runs its **lightweight extraction** path (service-level costs +
  AI-signal detection only); when billing is the sole source, it runs full processing.

If none of the three input types are present, the phase's `_preconditions` `_assert`
fails `_unrecoverable` (§ Gate protocol) — no fabricated discovery.

## Scope Boundary

**This phase covers Discover & Analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists in GCP. Nothing else.**
