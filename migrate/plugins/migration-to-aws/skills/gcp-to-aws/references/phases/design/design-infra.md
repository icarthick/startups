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
   lookup_direct_mapping(source_type=<gcp_type>, raw_config=<resource config from inventory>)
   ```

   The tool auto-extracts condition fields from raw_config (e.g., `database_version` → engine for Cloud SQL conditional mappings). You may also pass `condition_context` explicitly if preferred.

2. If `hit: true` → write the result into `aws-design.json`:
   - `aws_service` ← tool's `aws_service`
   - `confidence` ← `"deterministic"`
   - `human_expertise_required` ← `false`
   - Done for this resource. Do not proceed to Pass 2.

3. If `hit: false` → proceed to Pass 2 (tool-based selection).

**Definitions:** `deterministic` = direct mapping hit (unconditional). `inferred` = decided by recommend tools via normalize→recommend flow. `billing_inferred` = billing-only path.

### Pass 2: Tool-Based Selection

For resources not covered by fast-path:

**Note:** Any resource reaching Pass 2 has already been checked by `lookup_direct_mapping` in Pass 1 (deferred, skip, and direct cases are resolved there). Proceed directly to normalization.

**1. Normalize the resource:**

Call the `normalize_resource` MCP tool:

```
normalize_resource(source_type=<gcp_type>, raw_config=<resource config from inventory>)
```

This returns:

- `archetype` — the workload pattern (`relational-db`, `container`, `function`, `vm`, `load-balancer`, `message-broker`, etc.)
- `next_tool` — which recommend tool to call (`recommend_database`, `recommend_compute`, `recommend_networking`, `recommend_messaging`, or `null`)
- `canonical_fields` — deterministically extracted fields ready for the tool
- `requires_inference` — fields the LLM must infer before calling (e.g., `workload_pattern`, `delivery_pattern`, `subscriber_count`)

If `normalize_resource` returns an error (unknown source type) or `next_tool` is null (no recommend tool for this archetype):

> Use your knowledge of AWS services to select the best fit. Consider feature compatibility with the source, affinity with other resources in this cluster, and prefer simpler architectures. Set `confidence: "inferred"` and add a warning: "Resource mapped without tool validation — review recommended."

**2. Infer required signals (LLM judgment):**

For each field in `requires_inference`, examine the raw resource config and determine:

- `workload_pattern`: `always-on` (min_instances > 0, long-running), `event-driven` (trigger-based, no min_instances), `batch` (scheduled, startup_script), `windows-only` (Windows OS image)
- `delivery_pattern` (messaging): `fan-out` (topic with multiple subscriptions), `point-to-point` (single consumer queue)
- `subscriber_count` (messaging): count subscriptions attached to the topic in the inventory
- If undetermined, pass `null` — the recommend tool will produce a best-effort answer.

Also read from `preferences.json`:

- `kubernetes_pref`: `design_constraints.kubernetes.value`
- `cost_sensitivity`: `design_constraints.cost_sensitivity.value`
- `availability`: `design_constraints.availability.value` (for database)
- `io_workload`: `design_constraints.db_io_workload.value` (for database)
- `traffic`: `design_constraints.database_traffic.value` (for database)
- `data_size_gb`: `design_constraints.db_size.value` midpoint (for database)

**3. Call the recommend tool indicated by `next_tool`:**

The `normalize_resource` response includes `next_tool` (e.g., `"recommend_database"`, `"recommend_compute"`, `"recommend_networking"`, or `"recommend_messaging"`). Call that tool with `canonical_fields` + inferred signals + preference values merged as inputs.

If `next_tool` is `null`: no recommend tool exists for this workload type yet. Apply the manual rubric from `design-refs/<category>.md` as fallback.

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

**IaC extraction note:** Only `single-az` and `multi-az` can be auto-extracted from Terraform (`ZONAL` / `REGIONAL`). **`multi-az-ha` and `multi-region` are never inferred from IaC** — they require explicit user intent via Q6. If `availability` is absent in preferences, pass `null` to the tool — it will return `needs_clarification`.

**5.** Write `human_expertise_required` from the tool response (or `true` if Pass 1 returned deferred/skip).

## Step 3: Handle Secondary Resources

For each SECONDARY resource:

1. Call `lookup_direct_mapping` (handles direct, skip, and deferred — same as primary resources)
2. If miss: call `normalize_resource` with `resolved_primaries` — pass the already-resolved primary resources from this cluster so the tool can handle parent-dependent decisions:

   ```
   normalize_resource(
     source_type=<gcp_type>,
     raw_config=<resource config>,
     resolved_primaries=[
       {"type": "google_container_cluster", "aws_service": "EKS", ...},
       {"type": "google_compute_network", "aws_service": "VPC", ...}
     ]
   )
   ```

   The `resolved_primaries` array should include every primary resource in this cluster that was resolved in Step 2 — each with at minimum `type` and `aws_service`.

3. If the response has `next_action: "skip"` → write a skip entry with the `skip_reason` and move on.
4. Otherwise → follow the same Pass 2 flow (infer signals, call `recommend_*`, write result).

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

Assemble `aws-design.json` from the results accumulated in Steps 2–3:

- Top level: `{ "clusters": [...], "warnings": [...] }`
- Each cluster: `cluster_id` (from source clusters), `gcp_region`, `aws_region` (from preferences), `resources` array
- Each resource: `gcp_address`, `gcp_type`, `gcp_config` (from inventory) + all fields from the tool response (`aws_service`, `aws_config`, `confidence`, `human_expertise_required`, `rubric_applied`) + a `rationale` string summarizing `rubric_applied`

Then call `validate_design` to confirm the output is structurally correct before proceeding.

## Output Validation

After writing `aws-design.json`, call the `validate_design` MCP tool:

```
validate_design(design=<aws-design.json content>, clusters_source=<gcp-resource-clusters.json content>)
```

- If `valid: true` → proceed to Completion Handoff Gate.
- If `valid: false` → review `violations` array. Fix the issues in `aws-design.json` and re-validate. Do not proceed until valid.

## Completion Handoff Gate (Fail Closed)

Before returning control to `design.md`, require:

- `aws-design.json` exists and `validate_design` returned `valid: true`.

If this gate fails: STOP and output: "design-infra did not produce a valid `aws-design.json`; do not complete Phase 3."

## Present Summary

After writing `aws-design.json`, present a concise summary to the user:

1. Total resources mapped and cluster count
2. Per-cluster table: GCP resource → AWS service (one line each). For how each mapping was chosen, use **plain English** from `design-refs/fast-path.md` → **User-facing vocabulary** — **Standard pairing** (`deterministic`), **Tailored to your setup** (`inferred`), or **Estimated from billing only** (`billing_inferred`). Lead with the bold phrase; include the JSON value in parentheses only if the user is technical.
3. Any warnings (regional fallbacks; call out **Tailored to your setup** rows that deserve extra review)
4. If any resource has **`Deferred — specialist engagement`**: state **prominently** that **no AWS analytics target was chosen**. Direct the user to **their AWS account team and/or a data analytics migration partner**. Do **not** recommend Athena, Redshift, Glue, or EMR in the chat summary.

Keep it under 20 lines. The user can ask for details or re-read `aws-design.json` at any time.
