---
_fragment: eks-generate
_of_phase: generate
_scope: >
  EKS Terraform + kubernetes/ manifest generation — the opt-in alternative to
  the Fargate compute path. NOT YET AUTHORED in the DSL refactor.
_produces: [terraform/eks.tf, kubernetes/]
_on_error:
  _halt_and_inform: { effect: "stop; surface diagnostic", status: retain_in_progress }
---

# Generate Fragment: EKS (NOT YET AUTHORED)

## Orientation

This fragment fires only when the phase's `eks-generate` `_trigger._when` is true
(`aws-design.json` has an `eks_cluster` entry or a service with
`aws_service == "EKS"`). The EKS generation branch is **not yet authored** in the
DSL refactor — the Fargate (default) path is complete; EKS is a tracked
cross-phase follow-up (design's EKS branch + estimate's EKS cost handling +
this). Authoring it is the port of upstream `generate-eks.md`: a
`templates/generate/terraform/eks.tf.tmpl` (cluster + node groups + helm/tls
providers, kept OUT of main.tf so the Fargate path stays dependency-clean) and
`templates/generate/kubernetes/` manifests (namespace + Deployment per formation).
Until then this unit only halts.

## Step: halt_unimplemented

This step always halts. Perform the `_halt_and_inform` error action: emit
`GATE_FAIL | phase=generate | field=aws-design.eks_cluster | reason=eks_not_implemented`
and STOP. Tell the user: EKS artifact generation is not yet implemented in this
DSL build. Either re-run clarify/design choosing `ecs-fargate`, or use the
markdown/MCP build which has the EKS branch. Do NOT silently generate a partial
or Fargate-substituted EKS deployment. Retain `phases.generate` as `in_progress`.
