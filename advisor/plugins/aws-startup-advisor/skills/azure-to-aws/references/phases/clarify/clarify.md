---
_phase: clarify
_title: "Clarify Migration Requirements"
_requires_phase: discover
_input:
  - azure-resource-inventory.json
  - azure-resource-clusters.json
_fragments:
  - _id: global
    _trigger: { _always: true }
    _file: phases/clarify/clarify-global.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - preferences.json
_advances_to: design
_interactive: true
_re_entry_guard:
  _stale_if_completed: design
  _stale_artifact: aws-design.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [azure-resource-inventory.json, azure-resource-clusters.json]
    _on_failure: _unrecoverable
  - _validate_json: [azure-resource-inventory.json, azure-resource-clusters.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: preferences.json
    _on_failure: _halt_and_inform
  - _validate_json: preferences.json
    _on_failure: _halt_and_inform
  - _assert: "all Validation Checklist items in clarify-assemble.md pass"
    _on_failure: _halt_and_inform
  - _assert: "every assumption-sheet row the user was shown appears in preferences.json with a disposition of DETECTED, PROPOSED, ESSENTIAL, or N/A, and a value that is either the user's answer or the documented default"
    _on_failure: _halt_and_inform
  - _assert: "global.target_region is set, and design_constraints.cpu_architecture is set with x86_64 as the recorded default unless the user chose otherwise"
    _on_failure: _halt_and_inform
  - _assert: "identity is set (Category J always fires); its value is the fresh IAM Identity Center re-invite path unless the user chose full Entra ID federation"
    _on_failure: _halt_and_inform
  - _assert: "if the inventory contains Windows VM images, any Microsoft.Sql/* resource, or a SQL-on-VM signature, then licensing is set (License Included vs BYOL via Dedicated Hosts); otherwise licensing is N/A and no licensing question was asked"
    _on_failure: _halt_and_inform
  - _assert: "if azure-resource-clusters.json assigns any cluster a pattern_id, the user confirmed or corrected that pattern on the assumption sheet and the confirmed value is recorded in preferences.json"
    _on_failure: _halt_and_inform
  - _assert: "if any Microsoft.Web/serverfarms plan hosts more than one Microsoft.Web/sites app, the isolation question was asked and its answer recorded; an absent answer means no split"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - aws-design.json
  - "terraform/**"
---

# Phase 2: Clarify Migration Requirements

## Orientation

Turn the inventory into an explicit, user-confirmed set of migration preferences via
an **assumption sheet**: every row states what was detected or proposed and its
default, and the user corrects only what is wrong. This is a wizard, not an
interrogation — the aim is the fewest questions that still make the design
defensible.

Four dispositions per row: **DETECTED** (read from the estate), **PROPOSED** (the
skill's recommendation, changeable), **ESSENTIAL** (cannot be defaulted; must be
answered), **N/A** (does not apply to this estate — shown so the user can see it was
considered).

Two Azure-specific categories that no sibling skill has:

- **Licensing (conditional).** N/A, and its rubric never loads, when there are no
  Windows VM images, no `Microsoft.Sql/*`, and no SQL-on-VM signature. When it
  fires: one ESSENTIAL question, License Included vs BYOL via Dedicated Hosts.
  Azure Edition Windows Server is a special case — no question, a hard blocker
  warning, because AWS Application Migration Service refuses the image until it is
  re-imaged.
- **Identity (always fires).** One shallow question, defaulting to `[A]`: a fresh
  IAM Identity Center re-invite. Full Entra ID federation exists as option `[B]` but
  is not the assumed path.

Two more things the sheet must carry, because they are not inferable and both move
the estimate by multiples:

- **App Service Plan isolation.** A plan is the compute unit; its apps are
  deployments onto it and share its capacity. The default is no split. A split is
  only ever a stated isolation requirement, and when the user asks for one the
  rationale must say plainly that compute cost rises.
- **Cluster pattern confirmation.** Pattern recognition is judgment and will
  sometimes be wrong. Routing it through this sheet makes the holistic call
  user-validated before Design commits, at the cost of one sheet section and no new
  interaction model.

## Status — skeleton (build step 1)

Wiring only: one fragment gathers global answers, the assembler writes
`preferences.json`.

| Lands in | What                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------ |
| step 4   | The pattern-confirmation sheet section                                                            |
| step 5   | The per-category fragments — compute, database (with the availability selector), licensing (conditional), identity, AI, and the AI-only entry path |

The `_postconditions` above already assert the finished contract, so a category
landing later cannot land silently: its assert fails until the fragment exists.

## Step: Run the phase

1. Run each fragment whose `_trigger` holds, presenting its sheet section.
2. Run `clarify-assemble.md`.
3. Evaluate `_postconditions`. On all-pass emit `HANDOFF_OK`; on any failure emit
   `GATE_FAIL` and stop.
