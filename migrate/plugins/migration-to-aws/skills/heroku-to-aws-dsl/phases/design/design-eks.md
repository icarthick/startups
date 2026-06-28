---
_fragment: eks-mapping
_of_phase: design
_scope: >
  EKS (Kubernetes) compute mapping for all formations — the opt-in alternative
  to the default Fargate path. NOT YET AUTHORED in the DSL refactor.
_produces: [aws-design.json]
_on_error:
  _halt_and_inform: { effect: "stop; surface diagnostic", status: retain_in_progress }
---

# Design Fragment: EKS Mapping (NOT YET AUTHORED)

## Orientation

This fragment fires only when the phase's `eks-mapping` `_trigger._when` is true
(`design_constraints.kubernetes.value` is `eks-managed` or `eks-or-ecs`). The EKS
compute branch is **not yet authored** in the DSL refactor — the Fargate
(default) path is complete; EKS is a tracked follow-up. Authoring it is the
all-or-nothing port of upstream `design-eks.md` + `eks-mapping-table.md` into a
DSL fragment + a `knowledge/design/eks-pod-sizing.json` table, sized from all
formations with a single post-loop `eks_cluster` aggregate (mirror the MCP
refactor's EKS port). Until then this unit only halts.

## Step: halt_unimplemented

This step always halts. Perform the `_halt_and_inform` error action: emit
`GATE_FAIL | phase=design | field=design_constraints.kubernetes | reason=eks_not_implemented`
and STOP. Tell the user: the EKS compute target is not yet implemented in this
DSL build of the heroku-to-aws skill. Either re-run clarify and choose
`ecs-fargate`, or use the markdown/MCP build of the skill which has the EKS
branch. Do NOT silently fall back to Fargate (that would misrepresent the user's
explicit EKS choice). Retain `phases.design` as `in_progress`.
