---
_assemble: assemble-design
_of_phase: design
_reads:
  - infra (fragment contribution)
_produces:
  - aws-design.json
---

# Design — Assemble Design

> **Assembler unit.** The single creator of `aws-design.json` and the owner of its
> final contract. See `design.md` for how it is composed into the phase.

## Assembly rules

1. Merge fragment contributions into one `aws-design.json`.
2. **Cluster-level fields come first in the artifact and first in the report**:
   `pattern_id`, `target_architecture`, the cluster `rationale`, and the constraint
   set the pattern imposed. Per-resource rows follow.
3. Per-resource rows carry `azure_id` and `azure_type` — not a Terraform address.
   The ARM resource ID is a better stable address: it embeds subscription and
   resource group, so one field supplies the cluster key, the environment scope, and
   uniqueness with no derivation.
4. Set `confidence` per row from the tier that produced it, and record
   `rubric_applied` when pass 2 ran.
5. Validate secondaries against regional availability and feature parity via the
   awsknowledge MCP. This is non-blocking: a failed check becomes a warning, not a
   gate failure.
6. Re-check the invariant before writing: no `deterministic` row's `aws_service` was
   changed by a pattern constraint.

## Report shape

The customer-facing report leads with cluster-level rationale, not a 40-row mapping
table. Per-resource rows move to an appendix. This is the visible payoff of the
holistic goal, and it is the part a customer actually reads. An `unclassified`
pattern is a required fallback, not a failure — but it must be flagged so the output
does not overclaim architectural insight it does not have.

## Status — skeleton (build step 1)

Writes the artifact and owns the contract above. Cluster-level fields land with
step 4; the AI design route lands with step 6.
