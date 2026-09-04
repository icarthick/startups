---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - azure-resource-inventory.json
  - azure-resource-clusters.json
  - preferences.json
_knowledge:
  - { file: knowledge/design/fast-path-services.json }
_fragments:
  - _id: infra
    _trigger: { _always: true }
    _file: phases/design/design-infra.md
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - aws-design.json
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
  - _check_file_exists: [azure-resource-inventory.json, azure-resource-clusters.json, preferences.json]
    _on_failure: _unrecoverable
  - _validate_json: [azure-resource-inventory.json, azure-resource-clusters.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: aws-design.json
    _on_failure: _halt_and_inform
  - _validate_json: aws-design.json
    _on_failure: _halt_and_inform
  - _assert: "aws-design.json has phase == 'design' and a valid timestamp; services[] is present (empty only if every resource was deferred or skipped)"
    _on_failure: _halt_and_inform
  - _assert: "every services[] entry has service_id, azure_id, azure_type, aws_service, aws_config, confidence, and rationale; confidence is one of deterministic, measured, inferred, billing_inferred"
    _on_failure: _halt_and_inform
  - _assert: "every entry whose confidence is 'deterministic' matches a row in the Direct Mappings table, and no pattern constraint changed its aws_service — a pattern may narrow rubric candidates and may never override a deterministic mapping"
    _on_failure: _halt_and_inform
  - _assert: "every cluster in azure-resource-clusters.json appears in clusters[] with pattern_id, target_architecture, a cluster-level rationale, and the constraint set the pattern imposed"
    _on_failure: _halt_and_inform
  - _assert: "no Microsoft.Web/sites resource carries its own compute sizing in aws_config unless preferences.json records an explicit isolation split for its plan; the compute line belongs to the Microsoft.Web/serverfarms plan"
    _on_failure: _halt_and_inform
  - _assert: "every resource in the inventory is accounted for: mapped in services[], deferred in deferred[], or recorded in warnings[] as a skip or as an edge-bearing config source that was consumed"
    _on_failure: _halt_and_inform
  - _assert: "iac_metadata.untranslated_types is empty; a type Discover could not name is treated as cost-bearing and STOPs the design, because the skill cannot demonstrate that a resource it could not identify is free"
    _on_failure: _halt_and_inform
  - _assert: "every deferred[] entry carries aws_service 'Deferred — specialist engagement' and a reason, and carries NO confidence field — a deferral did not come from a rubric"
    _on_failure: _halt_and_inform
  - _assert: "AWS App Runner does not appear as a target anywhere in aws-design.json"
    _on_failure: _halt_and_inform
  - _assert: "every entry whose confidence is 'measured' cites the utilization evidence that backed it"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md
  - estimation-infra.json
---

# Phase 3: Design AWS Architecture

## Orientation

Turn the inventory, the clusters, and the confirmed preferences into
`aws-design.json`. Two product goals have to hold at once, and they pull against each
other the moment a workload-level decision disagrees with a per-resource one:

1. **Holistic** — the output describes workloads, not independent rows.
2. **Pre-determined where there is no ambiguity** — an unambiguous service is not
   routed through a rubric that could reason its way to a different answer.

The precedence order below is what reconciles them.

## Precedence order

1. **Skip Mappings** — not a target at all.
2. **Specialist gates → `Deferred`.** "We do not know" must never be overridden by
   anything below it.
3. **Eliminators** — hard technical blockers. Lambda's 15-minute ceiling is physics,
   not a preference.
4. **Direct Mappings → `deterministic`** — the pre-determined recommendations.
5. **Pattern constraint** — the holistic layer, applied to whatever is left.
6. **Six-criteria rubric** — chooses *within* the pattern's candidate set:
   Eliminators, Operational Model, User Preference, Feature Parity, Cluster Context,
   Simplicity, applied in order, first match wins.
7. **Preferred-target substitution.**
8. **Post-selection** — right-sizing from measured utilization, then CPU
   architecture.

> **INVARIANT: a pattern may never change a `deterministic` mapping's target. It may
> only choose among rubric candidates.**

If a pattern could override a fast-path row, the `deterministic` tier would stop
meaning anything and its user-facing label ("Standard pairing") would be false. So a
genuine pattern/fast-path conflict is evidence the row does not belong in Direct
Mappings — the fix is to demote the row, never to let the pattern win.

Right-sizing is **post-selection, not a seventh criterion.** The six criteria select
a *service* and never touch capacity; adding a seventh would break "apply in order,
first match wins". Each rubric file gets an additive `## Right-Sizing` section,
structurally parallel to `## CPU Architecture`.

## Status — build step 3 (pass 1 only)

**Pass 1 is real.** `knowledge/design/fast-path-services.json` carries the Direct
Mappings, Skip Mappings, and specialist-gate rows; `design-refs/fast-path.md` is their
contract; `design-refs/index.md` routes everything else. **Pass 2 — the category rubric
files — does not exist yet**, so on any estate carrying compute or a relational
database this phase **halts** rather than improvising a target. See `index.md`'s halt
guard, which is the same guard and the same reasoning as `discover-iac.md` Step 2.

| Lands in | What                                                                                                     |
| -------- | -------------------------------------------------------------------------------------------------------- |
| step 4   | Pattern consumption at cluster level; the cluster-level `data-pipeline` gate                               |
| step 5   | The per-category rubric files named by `index.md`, and the `knowledge/*.json` sizing tables wired through `_knowledge` `_when` guards |
| step 6   | The AI design route                                                                                       |

Step 3 came before the rubric content deliberately: the precedence order and the
admission test decide what each rubric file has to cover, and getting the Direct
Mappings row set wrong makes every downstream confidence label wrong.

The `_postconditions` above encode the FINISHED contract, so several of them fail today
by construction — a halted design does not account for every resource, and it may carry
a non-empty `pending_rubric[]`. That is the intended behaviour: the gate reports the
skill's gap loudly instead of letting a plausible mapping pass for a real one.

## Step: Run the phase

1. Order clusters by tier: network/identity/secrets → data → compute → edge.
2. Run each fragment whose `_trigger` holds.
3. Run `design-assemble.md`.
4. Evaluate `_postconditions`. On all-pass emit `HANDOFF_OK`; on any failure emit
   `GATE_FAIL` and stop.
