---
_fragment: eks-mapping
_of_phase: design
_scope: >
  When the EKS compute path is selected, map every formation to an EKS Deployment
  entry and produce the single eks_cluster aggregate. Writes _eks-design.json (the
  assembler merges it into aws-design.json). ONLY this — no non-formation mapping,
  no VPC, no Fir (mapping-engine owns those). Does NOT update .phase-status.json.
_produces: [_eks-design.json]
_postconditions:
  - _validate_json: _eks-design.json
  - _assert: "_eks-design.json has eks_services[] and eks_cluster"
  - _assert: "every eks_services[] entry has service_id, source_resource_id, heroku_app, aws_service=='EKS', confidence, aws_config with resources.requests/limits + replicas + node_group_type"
  - _assert: "exactly one eks_cluster with cluster_name, kubernetes_version, node_group_type, node_groups[] (min/max/desired sized from all formations), addons[]"
  - { _assert: "every formation's dyno_type resolved in eks-pod-sizing.json (else warned + excluded)", _on_failure: _warn_and_skip }
_on_error:
  _warn_and_skip:  { effect: "record warning; skip this formation; continue", status: continue }
  _unrecoverable:  { effect: "stop; surface error",                          status: revert_to_pending }
---

# Design Fragment: EKS Mapping

## Orientation

The EKS-compute FRAGMENT. Fires only when the phase's `eks-mapping` trigger is
true (`design_constraints.kubernetes.value` is `eks-managed` or `eks-or-ecs`).
When EKS is selected it is ALL-OR-NOTHING: every formation maps to an EKS
Deployment (NOT Fargate), and a SINGLE `eks_cluster` is sized from all
formations. This fragment reads `heroku-resource-inventory.json` +
`preferences.json` + `knowledge/design/eks-pod-sizing.json` and CREATES
`_eks-design.json`; the design assembler MERGES that into `aws-design.json`
(folding the EKS services in + adding the `eks_cluster` key). Non-formation
mapping (postgres→RDS, redis→ElastiCache, kafka→MSK, addons→fast-path), VPC, and
Fir are the mapping-engine fragment's job — NOT this one. DETERMINISM: pod
requests/limits/node-type are DIRECT LOOKUPS from `eks-pod-sizing.json`; node
counts are the documented `node_sizing` formula. Does NOT update
`.phase-status.json`.

## Step: map_formations_to_pods

```meta
_for_each: inventory formation resources
_collect: [eks_services, warnings, node_types_seen, total_pods]
_knowledge: [knowledge/design/eks-pod-sizing.json]
```

For each `resource_type == "formation"` resource, look up `config.dyno_type` in
`eks-pod-sizing.json.rows` (exact, case-insensitive). NOT found → warn per
`_on_not_found`, produce no entry, continue (`_warn_and_skip`). Found → read
`req_cpu`/`req_mem`/`lim_cpu`/`lim_mem`/`node_type` DIRECTLY from the row. Append
an EKS service entry (shape per `aws-design.schema.json`):

```json
{ "service_id": "eks:{app}:{process_type}", "source_resource_id": "{resource_id}",
  "heroku_app": "{app}", "aws_service": "EKS", "confidence": "deterministic",
  "aws_config": { "region": "{region}", "cluster_name": "heroku-migration-cluster",
    "namespace": "{app}", "deployment_name": "{process_type}",
    "replicas": <config.quantity clamped 0-100>, "container_image": "placeholder:{app}-{process_type}",
    "process_type": "{process_type}",
    "resources": { "requests": {"cpu": <req_cpu>, "memory": <req_mem>}, "limits": {"cpu": <lim_cpu>, "memory": <lim_mem>} },
    "load_balancer": <true iff process_type=='web'>, "node_group_type": "<resolved below>" } }
```

Collect each formation's `node_type` into `node_types_seen` and its `replicas`
into `total_pods` for the post-loop cluster sizing.

(Empty-Procfile / no-formation app → same reject as the Fargate path: warn, no
entries. If NO formation maps, this fragment still writes an `eks_cluster` only
if ≥1 EKS service exists; otherwise it produces no `_eks-design.json` and the
assembler treats EKS as absent.)

## Step: size_cluster_and_write

```meta
_writes: _eks-design.json
_knowledge: [knowledge/design/eks-pod-sizing.json]
```

Build the single `eks_cluster` aggregate from the collected data + the
`cluster` / `node_sizing` rules in `eks-pod-sizing.json`:

- `cluster_name` = `cluster.cluster_name`; `kubernetes_version` =
  `cluster.kubernetes_version` (the documented constant).
- `node_group_type` = `cluster.node_group_type_by_pref[kubernetes.value]`
  (`eks-managed`→`self-managed`, `eks-or-ecs`→`managed`). Set the same value on
  every EKS service entry's `aws_config.node_group_type`.
- node group: `instance_types` = `[ the node_type of the LARGEST dyno present ]`
  per `node_sizing.instance_type` (largest by `_node_size_rank`); `min_size` = 2;
  `desired_size` = max(min_size, ceil(total_pods / 4)) — clamp UP to min_size (AWS
  rejects desired < min); `max_size` = max(desired_size, min_size) + 2.
- `addons` = `cluster.addons`.

Write `$MIGRATION_DIR/_eks-design.json`:

```json
{ "eks_services": [ <the entries above> ],
  "eks_cluster": { "cluster_name": "...", "kubernetes_version": "1.31",
    "node_group_type": "...", "node_groups": [ { "name": "general",
      "instance_types": ["..."], "min_size": 2, "max_size": <n>, "desired_size": <n> } ],
    "addons": ["vpc-cni","coredns","kube-proxy","aws-load-balancer-controller"] } }
```

This is a `_`-prefixed intermediate artifact (the assembler folds it into
`aws-design.json` and it is not a final phase output).
