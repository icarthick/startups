---
_fragment: eks-generate
_of_phase: generate
_scope: >
  Emit EKS Terraform (eks.tf + helm-provider.tf) and kubernetes/ manifests
  (namespace + per-formation deployments + web services) from an EKS design, and
  add EKS sections to MIGRATION_GUIDE.md. ONLY this. Does NOT update
  .phase-status.json.
_produces: [terraform/eks.tf, terraform/helm-provider.tf, kubernetes/]
_postconditions:
  - _check_file_exists: [terraform/eks.tf, terraform/helm-provider.tf]
  - _assert: "exactly one node-group block in eks.tf per design.eks_cluster.node_group_type (managed XOR self-managed)"
  - _assert: "kubernetes/ has a namespace.yaml per heroku_app, a deployment per EKS service, and a web service manifest per web EKS service"
  - _assert: "no {{...}} placeholder remains in eks.tf / helm-provider.tf / any kubernetes/*.yaml"
  - _assert: "helm/tls providers are in helm-provider.tf, NOT main.tf (Fargate path stays dependency-clean)"
_on_error:
  _warn_and_skip:  { effect: "log to generation-warnings.json; continue", status: continue }
  _unrecoverable:  { effect: "stop; surface error",                       status: revert_to_pending }
---

# Generate Fragment: EKS

## Orientation

The EKS-generation FRAGMENT. Fires only when the phase's `eks-generate` trigger
is true (`aws-design.json` has an `eks_cluster` entry / services with
`aws_service == "EKS"`). It emits the EKS Terraform (`terraform/eks.tf` +
`terraform/helm-provider.tf`) and the `kubernetes/` manifests from the
`templates/generate/terraform/eks.tf.tmpl` / `helm-provider.tf.tmpl` /
`templates/generate/kubernetes/*.tmpl` skeletons, and adds EKS sections to
MIGRATION_GUIDE.md. The helm/tls providers go in their OWN file (NOT main.tf) so
the default Fargate path stays dependency-clean. Does NOT update
`.phase-status.json`.

## Step: emit_eks_terraform

```meta
_templates: [templates/generate/terraform/eks.tf.tmpl, templates/generate/terraform/helm-provider.tf.tmpl]
```

Fill `eks.tf.tmpl` from `aws-design.json.eks_cluster` + `vpc_design`:
`{{cluster_name}}`, `{{kubernetes_version}}`, `{{subnet_refs}}` (per
`vpc_design.mode`), `{{vpc_id_reference}}`, `{{vpc_cidr_block}}`, and the node
group fields (`{{node_instance_types_hcl}}` = `node_groups[0].instance_types` as
an HCL list; `{{node_instance_type_primary}}` = its first element;
`{{min_size}}`/`{{max_size}}`/`{{desired_size}}`).

**Emit EXACTLY ONE node-group block** per `eks_cluster.node_group_type`:
`managed` → keep ONLY the `aws_eks_node_group` block (drop the launch-template +
ASG + nodes SG blocks); `self-managed` → keep ONLY the launch-template + ASG +
nodes SG blocks (drop `aws_eks_node_group`). The cluster/IAM/OIDC/LB-controller/
cluster-SG blocks are always kept. Write `terraform/eks.tf`.

Write `terraform/helm-provider.tf` verbatim (the helm + tls provider block) —
NOT into main.tf.

## Step: emit_kubernetes_manifests

```meta
_templates: [templates/generate/kubernetes/namespace.yaml.tmpl, templates/generate/kubernetes/deployment.yaml.tmpl, templates/generate/kubernetes/service.yaml.tmpl]
```

For each EKS service in `aws-design.json` (`aws_service == "EKS"`):

- Write `kubernetes/namespace.yaml` ONCE per unique `heroku_app` (`{{heroku_app}}`).
- Write `kubernetes/{app}-{process_type}-deployment.yaml` per service, filling
  `{{replicas}}`, `{{container_image}}`, and the resource requests/limits from
  the service's `aws_config.resources` (`{{req_cpu}}`/`{{req_mem}}`/`{{lim_cpu}}`/
  `{{lim_mem}}`). Include `{{ports_block}}` (the `ports: containerPort 8080`
  block) ONLY for `process_type == "web"`, else leave it empty.
- Write `kubernetes/{app}-web-service.yaml` ONLY for web services
  (`load_balancer == true`).

Confirm no `{{...}}` remains in any emitted file.

## Step: add_guide_sections

Append the EKS sections to `MIGRATION_GUIDE.md` (after Prerequisites, before
Data Migration): "EKS Cluster Setup" (terraform apply, `aws eks
update-kubeconfig`, verify nodes + LB controller), "Deploy Workloads to EKS"
(`kubectl apply -f kubernetes/`, verify pods + svc), and \u2014 only when data stores
exist in the design \u2014 "Configure Pod-to-Service Access" (IRSA, the
Terraform-created pod\u2192RDS/ElastiCache/MSK SG rules, K8s Secrets). Add the
recommended-next-steps note (liveness/readiness probes, HPA, tune limits).
