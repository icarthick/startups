# EKS Cross-Phase Pass — VERDICT

**Change:** Authored the opt-in EKS compute path across design + generate
(estimate's EKS handling existed but was untested). EKS is selected via clarify's
`design_constraints.kubernetes.value` ∈ {`eks-managed`, `eks-or-ecs`} and is
ALL-OR-NOTHING: every formation maps to an EKS Deployment (not Fargate), with a
single `eks_cluster` aggregate sized from all formations. Mirrors the MCP
refactor's PR #85 (pods $0, post-loop cluster, helm/tls isolated, k8s version a
documented constant).

Files:

- `knowledge/design/eks-pod-sizing.json` — 19-row dyno→pod requests/limits/
  node-type table + node-sizing rules + cluster config (k8s 1.31 constant,
  node_group_type-by-preference, addons).
- `phases/design/design-eks.md` — replaced the loud-halt stub with the real EKS
  fragment: per-formation EKS pod entries + the post-loop `eks_cluster` aggregate;
  writes its OWN `_eks-design.json`.
- `phases/design/design-mapping.md` — in EKS mode, skip the Fargate formation
  branch (still maps non-formation + VPC + Fir).
- `phases/design/design-assemble.md` — now a MERGER: folds `_eks-design.json`
  into `aws-design.json` (the discover-style shape) + all-or-nothing gate.
- `schemas/aws-design.schema.json` — added `eks_cluster`.
- `templates/generate/terraform/{eks.tf,helm-provider.tf}.tmpl` +
  `templates/generate/kubernetes/{namespace,deployment,service}.yaml.tmpl`.
- `phases/generate/generate-eks.md` — replaced the stub with the real EKS
  generate fragment (eks.tf managed-XOR-self-managed, helm provider in its own
  file, k8s manifests, guide sections).

## Design shape (discover-style merge — confirmed with the user)

Two fragments, each its OWN artifact, assembler merges (one creator per
artifact): `mapping-engine` creates `aws-design.json` (no EKS formations);
`eks-mapping` creates `_eks-design.json`; `design-assemble` merges. This honors
the taxonomy where a single fragment branching the formation handler would have
been simpler but a second fragment writing the same artifact would have violated
one-creator-per-artifact.

## Cold-LLM tests: PASS (one design defect + two estimate seams fixed)

**Design path** (eks-managed fixture: web standard-2x×2, worker standard-1x×1,
postgres standard-0): two-fragment-merge worked — pod requests/limits direct
lookups (web 500m/1024Mi/1000m/1024Mi m6i.large; worker 250m/512Mi m6i.large),
postgres→RDS (multi-az, not Aurora; not in the EKS fragment), all-or-nothing held
(no Fargate entries), merged design schema-valid → HANDOFF_OK.

**Estimate + generate paths** (merged EKS design): EKS pods cost **$0** (compute
billed once via the cluster nodes — NOT double-counted); cluster = control plane
$73 + m6i.large $70.08 × desired_size; generate fired eks-generate, emitted eks.tf
(self-managed node group only — managed block dropped), helm-provider.tf
(helm/tls isolated from main.tf), and namespace + 2 deployments + 1 web service
with per-service req/lim → HANDOFF_OK.

## Findings (fixed)

1. **Node sizing produced `desired_size(1) < min_size(2)` (REAL design defect,
   FIXED).** `ceil(total_pods/4)` for small workloads (≤4 pods) yields a desired
   below min — invalid in AWS ASG/node groups. Fixed: `desired_size =
   max(min_size, ceil(total_pods/4))`; `max_size = max(desired_size, min_size) +
   2`. (In `eks-pod-sizing.json` + the fragment prose.)
2. **EKS estimate NAT double-count seam (REAL, FIXED).** The post-loop NAT bullet
   AND the EKS branch both said to add NAT → a literal reading added it twice.
   Fixed: NAT (and the web ALB) are added ONCE by their own lines; the EKS branch
   explicitly does NOT re-add them.
3. **EKS cluster `node_count` unspecified (REAL, FIXED).** "node_rate ×
   node_count" didn't name desired/min/max (could diverge ~$140/mo). Pinned
   `node_count = eks_cluster.node_groups[0].desired_size` in the cost engine +
   the pricing-JSON formula.
4. **Observability had no EKS pod log-volume row (minor, FIXED).** Added
   `eks_pod_service: 3` to `log_volume_gb_per_service`.

## Net

The EKS cross-phase path is authored and cold-validated end-to-end: design
(two-fragment merge + sizing), estimate (pods $0 + post-loop cluster, no
double-count), generate (eks.tf + manifests, providers isolated). The
discover-style merge shape works for an alternative compute path; the all-or-
nothing invariant is gated. One design defect (sub-min desired) and two estimate
seams (NAT double-count, unspecified node_count) — all caught by the cold tests
and fixed. **All six phases now support both compute paths (Fargate + EKS).**
Remaining: optional CI validator + the clarify `migration_urgency` loose end.
