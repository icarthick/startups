# Design Phase: Infrastructure Mapping

> Loaded by `design.md` when `gcp-resource-inventory.json` and `gcp-resource-clusters.json` exist.

**Execute ALL steps in order. Do not skip or optimize.**

## Step 0: Validate Inputs

Read `preferences.json`. If missing: **STOP**. Output: "Phase 2 (Clarify) not completed. Run Phase 2 first."

Read `gcp-resource-clusters.json`.

## Step 1: Order Clusters

Sort clusters by `creation_order_depth` (lowest first, representing foundational infrastructure).

## Step 2: Two-Pass Mapping per Cluster

For each cluster, process `primary_resources` first, then `secondary_resources` (as classified during discover phase — see `gcp-resource-clusters.json`).

### Pass 1: Direct Mapping Lookup

For each PRIMARY resource in the cluster:

1. Call the `lookup_direct_mapping` MCP tool:

   ```
   lookup_direct_mapping(source_type=<gcp_type>, condition_context=<optional>)
   ```

   For `google_sql_database_instance`, extract the engine from `database_version` and pass as `condition_context`: `{"engine": "postgres"}`, `{"engine": "mysql"}`, or `{"engine": "sqlserver"}`.

2. If `hit: true` → write the result into `aws-design.json`:
   - `aws_service` ← tool's `aws_service`
   - `confidence` ← `"deterministic"`
   - `human_expertise_required` ← `false`
   - Done for this resource. Do not proceed to Pass 2.

3. If `hit: false` → proceed to Pass 2 (tool-based selection).

**Definitions:** `deterministic` = direct mapping hit (unconditional). `inferred` = decided by recommend tools via normalize→recommend flow. `billing_inferred` = billing-only path.

### Pass 2: Tool-Based Selection

For resources not covered by fast-path:

**0. BigQuery specialist gate (mandatory — before tools):** If `gcp_type` **starts with** `google_bigquery_`:

1. **Do not** recommend a specific AWS analytics or warehouse service (Athena, Redshift, Glue, EMR, Lake Formation, or a prescribed "data lake on S3" architecture).
2. Set `aws_service` to **`Deferred — specialist engagement`**, `human_expertise_required` to **`true`**, `confidence` to **`inferred`**, and `aws_config` to include `specialist_engagement` (text: engage **AWS account team** and/or **data analytics migration partner** before choosing any AWS target) and `no_automated_aws_target`: `true`. Set `rubric_applied` to `["BigQuery specialist gate — no automated AWS service target"]`.
3. **Skip** the normalize/recommend steps below for this resource.

**1. Normalize the resource:**

Call the `normalize_resource` MCP tool:

```
normalize_resource(source_type=<gcp_type>, raw_config=<resource config from inventory>)
```

This returns:

- `canonical_workload` — which recommend tool to call (`relational-db` → `recommend_database`, `container`/`function`/`vm`/`kubernetes` → `recommend_compute`)
- `canonical_fields` — deterministically extracted fields ready for the tool
- `requires_inference` — fields the LLM must infer before calling (e.g., `workload_pattern`)

If `normalize_resource` returns an error (unknown source type): check resource name patterns (scheduler → orchestration, log → monitoring). If no pattern match: **STOP** and output error.

**2. Infer required signals (LLM judgment):**

For each field in `requires_inference`, examine the raw resource config and determine:

- `workload_pattern`: `always-on` (min_instances > 0, long-running), `event-driven` (trigger-based, no min_instances), `batch` (scheduled, startup_script), `windows-only` (Windows OS image)
- If undetermined, pass `null` — the recommend tool will produce a best-effort answer.

Also read from `preferences.json`:

- `kubernetes_pref`: `design_constraints.kubernetes.value`
- `cost_sensitivity`: `design_constraints.cost_sensitivity.value`
- `availability`: `design_constraints.availability.value` (for database)
- `io_workload`: `design_constraints.db_io_workload.value` (for database)
- `traffic`: `design_constraints.database_traffic.value` (for database)
- `data_size_gb`: `design_constraints.db_size.value` midpoint (for database)

**3. Call the appropriate recommend tool:**

Route by `canonical_workload`:

| `canonical_workload`                                      | Tool                                                    | Key inputs                                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `relational-db`                                           | `recommend_database`                                    | engine, availability, size_class, io_workload, traffic, data_size_gb                                              |
| `container`, `function`, `vm`, `kubernetes`, `app-engine` | `recommend_compute`                                     | service_type, timeout_seconds, vcpu, memory_gb, gpu, runtime, workload_pattern, kubernetes_pref, cost_sensitivity |
| `nosql-document`                                          | _(v1: DynamoDB unless >100 txn items — apply manually)_ | —                                                                                                                 |

Merge `canonical_fields` + inferred signals + preference values → call the tool.

**4. Handle the response:**

- If `needs_clarification` → **STOP**. Output the reason and return to Clarify.
- If `error` → **STOP**. Output the error message.
- If `tie_break_required: true` → review `alternatives`, select based on Cluster Context (affinity with other resources in this cluster) and Simplicity (fewer resources preferred). Add rationale for your choice.
- Otherwise → write the result directly into `aws-design.json`:
  - `aws_service` ← tool's `aws_service`
  - `aws_config` ← tool's `aws_config`
  - `confidence` ← `"inferred"`
  - `human_expertise_required` ← tool's value (or `false`)
  - `rationale` ← summarize from `rubric_applied` array
  - `rubric_applied` ← tool's `rubric_applied`

**All invariants are enforced by the tools:** Q6 sole family selector (database), eliminators (compute), App Runner forbidden, Fargate sizing validation, engine compatibility. The LLM's role is: normalize, infer signals, call tools, break ties, write output.

**IaC extraction note:** Only `single-az` and `multi-az` can be auto-extracted from Terraform (`ZONAL` / `REGIONAL`). **`multi-az-ha` and `multi-region` are never inferred from IaC** — they require explicit user intent via Q6.

**5. Set `human_expertise_required`**: If the BigQuery specialist gate applied, already `true`. If a recommend tool returned it as `true`, keep it. Otherwise `false`. This field is REQUIRED on every resource.

**6. Preferred AWS target check**: **Skip** if `aws_service` is **`Deferred — specialist engagement`**. **Skip** for resources handled by recommend tools (they already enforce preferred targets). For remaining resources (networking, storage, messaging mapped via manual rubric), verify against the Preferred AWS Target Services table in `design-refs/fast-path.md`.

## Step 3: Handle Secondary Resources

For each SECONDARY resource:

1. Use `design-refs/index.md` for category
2. Apply fast-path (most secondaries have deterministic mappings)
3. If rubric needed: apply the **BigQuery specialist gate** (Pass 2 step 0) first when `gcp_type` starts with `google_bigquery_`; otherwise apply the same 6-criteria approach as Pass 2

## Step 3.5: Validate AWS Architecture (using awsknowledge)

If `aws_service` is **`Deferred — specialist engagement`**, **do not** validate against concrete AWS analytics SKUs; add a `warnings[]` entry that specialist engagement is required.

**Validation checks** (if awsknowledge available):

For each mapped AWS service, verify:

1. **Regional Availability**: Is the service available in the target region (e.g., `us-east-1`)?
   - Use awsknowledge to check regional support
   - If unavailable: add warning, suggest fallback region

2. **Feature Parity**: Do required features exist in AWS service?
   - Match GCP features from `preferences.json` design_constraints
   - Check AWS feature availability via awsknowledge
   - If feature missing: add warning, suggest alternative service

3. **Service Compatibility**: Are there known issues or constraints?
   - Check best practices and gotchas via awsknowledge
   - Add to warnings if applicable

**If awsknowledge unavailable:**

- Set `validation_status: "skipped"` in output
- Note in summary: "Architecture validation unavailable (non-critical)"
- Continue with design (validation is informational, not blocking)

**If validation succeeds:**

- Set `validation_status: "completed"` in output
- List validated services in summary

## Step 4: Write Design Output

**File 1: `aws-design.json`**

```json
{
  "clusters": [
    {
      "cluster_id": "compute_instance_us-central1_001",
      "gcp_region": "us-central1",
      "aws_region": "us-east-1",
      "resources": [
        {
          "gcp_address": "google_compute_instance.web",
          "gcp_type": "google_compute_instance",
          "gcp_config": {
            "machine_type": "n2-standard-2",
            "zone": "us-central1-a",
            "boot_disk_size_gb": 100
          },
          "aws_service": "Fargate",
          "aws_config": {
            "cpu": "0.5",
            "memory": "1024",
            "region": "us-east-1"
          },
          "confidence": "inferred",
          "human_expertise_required": false,
          "rationale": "Rubric: Compute Engine → Fargate (example — not a Direct Mapping row; Cloud Run/Compute Engine use Pass 2)",
          "rubric_applied": [
            "Eliminators: PASS",
            "Operational Model: Managed Fargate",
            "User Preference: Speed (q2)",
            "Feature Parity: Full (always-on compute)",
            "Cluster Context: Standalone compute tier",
            "Simplicity: Fargate (managed, no EC2)"
          ]
        }
      ]
    }
  ],
  "warnings": [
    "service X not fully supported in us-east-1; fallback to us-west-2"
  ]
}
```

## Output Validation Checklist

- `clusters` array is non-empty
- Every cluster has `cluster_id` matching a cluster from `gcp-resource-clusters.json`
- Every cluster has `gcp_region` and `aws_region`
- Every resource has `gcp_address`, `gcp_type`, `gcp_config`, `aws_service`, `aws_config`
- Every resource has `human_expertise_required` (boolean) — `true` for all `google_bigquery_*` resources (specialist gate); `false` for others unless a rubric explicitly requires it
- Every `google_bigquery_*` resource has `aws_service` exactly **`Deferred — specialist engagement`** (not Athena, Redshift, Glue, etc.)
- Every `google_sql_database_instance` resource has `aws_service` ∈ {`RDS PostgreSQL`, `RDS MySQL`, `Aurora PostgreSQL`, `Aurora MySQL`} with non-empty `rationale` citing Q6 availability value. If `availability` is `single-az` or `multi-az`, `aws_service` MUST be RDS (not Aurora). If `multi-az-ha` or `multi-region`, MUST be Aurora.
- All `confidence` values are either `"deterministic"` or `"inferred"`
- All `rationale` fields are non-empty
- Every resource from every evaluated cluster appears in the output
- No duplicate `gcp_address` values across clusters
- Output is valid JSON

## Completion Handoff Gate (Fail Closed)

Before returning control to `design.md`, require:

- `aws-design.json` exists and passes the Output Validation Checklist above.

If this gate fails: STOP and output: "design-infra did not produce a valid `aws-design.json`; do not complete Phase 3."

## Present Summary

After writing `aws-design.json`, present a concise summary to the user:

1. Total resources mapped and cluster count
2. Per-cluster table: GCP resource → AWS service (one line each). For how each mapping was chosen, use **plain English** from `design-refs/fast-path.md` → **User-facing vocabulary** — **Standard pairing** (`deterministic`), **Tailored to your setup** (`inferred`), or **Estimated from billing only** (`billing_inferred`). Lead with the bold phrase; include the JSON value in parentheses only if the user is technical.
3. Any warnings (regional fallbacks; call out **Tailored to your setup** rows that deserve extra review)
4. If any resource has **`Deferred — specialist engagement`**: state **prominently** that **no AWS analytics target was chosen**. Direct the user to **their AWS account team and/or a data analytics migration partner**. Do **not** recommend Athena, Redshift, Glue, or EMR in the chat summary.

Keep it under 20 lines. The user can ask for details or re-read `aws-design.json` at any time.
