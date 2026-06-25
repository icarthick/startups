# Discover Phase: IaC (Terraform) Discovery

> Self-contained IaC discovery sub-file. Scans for IaC files, extracts Terraform resources, classifies, builds dependency graphs, clusters, and generates output files.
> If no IaC files are found, exits cleanly with no output.

**Execute ALL steps in order. Do not skip or optimize.**

## Step 0: Self-Scan for IaC Files

Recursively scan the entire target directory tree for infrastructure files:

**Terraform:**

- `**/*.tf`, `**/*.tf.json` — resource definitions
- `**/*.tfvars`, `**/*.auto.tfvars` — variable values
- `**/*.tfstate` — state files (read-only, if present)
- `**/.terraform.lock.hcl` — lock files
- `**/modules/*/` — module directories and nested modules

**Contextual files** (recorded but not processed — useful for future discovery phases):

- **Kubernetes:** `**/k8s/*.yaml`, `**/kubernetes/*.yaml`, `**/manifests/*.yaml`
- **Docker:** `**/Dockerfile`, `**/docker-compose*.yml`
- **CI/CD:** `**/cloudbuild.yaml`, `**/.github/workflows/*.yml`, `**/.gitlab-ci.yml`, `**/Jenkinsfile`

Record file paths and types for all files found.

**Exit gate:** If NO Terraform files (`.tf`, `.tfvars`, `.tfstate`, `.terraform.lock.hcl`) are found, **exit cleanly**. Return no output artifacts. Other sub-discovery files may still produce artifacts.

**Secret hygiene (HARD — no exceptions):** `.tfstate` and `.tfvars` files may contain database passwords, API keys, TLS private keys, and certificate material in plaintext.

When `.tfstate` or `.tfvars` files are found:

1. **Warn the user immediately:** "Found [N] Terraform state/variable file(s). These may contain secrets. They will be read for resource discovery only — raw values will NOT be copied into any migration artifact."
2. **Redact sensitive attributes** before writing to `gcp-resource-inventory.json`. For any `gcp_config` field whose key matches a sensitive pattern (password, secret, key, token, credential, private_key, client_secret, access_key, api_key), replace the value with `"[REDACTED]"`.
3. **Never write raw secret values** into `gcp-resource-inventory.json`, `gcp-resource-clusters.json`, or any other output artifact.

Sensitive key patterns to redact (case-insensitive): `password`, `passwd`, `secret`, `api_key`, `apikey`, `access_key`, `private_key`, `client_secret`, `token`, `credential`, `auth`.

## Step 1: Extract Resources from Terraform

1. Read all `.tf`, `.tfvars`, and `.tfstate` files in working directory (recursively)
2. Extract all resources matching `google_*` pattern (e.g., `google_compute_instance`, `google_sql_database_instance`)
3. For each resource, capture exactly:
   - `address` (e.g., `google_compute_instance.web`)
   - `type` (e.g., `google_compute_instance`)
   - `name` (resource name component, e.g., `web`)
   - `config` (object with key attributes: `machine_type`, `name`, `region`, etc.)
   - `raw_hcl` (raw HCL text for this resource, needed for Step 4)
   - `depends_on` (array of addresses this resource depends on)
4. Also extract provider and backend configuration (for region detection)
5. Report total resources found to user (e.g., "Parsed 50 GCP resources from 12 Terraform files")

## Step 2: Detect AI Signals

Call the `detect_ai_signals` MCP tool with the resource list from Step 1:

```
detect_ai_signals(resources=<resource list from Step 1>)
```

Returns an `ai_detection` object (`has_ai_workload`, `confidence`, `confidence_level`, `signals_found`, `ai_services`). Save this for Step 7a (written into the `ai_detection` section of `gcp-resource-inventory.json`).

**Note:** This detects signals from Terraform resource types only. Full AI workload profiling (code analysis, billing data) is handled by `discover-app-code.md`.

## Step 3: Scan References and Cluster

### 3a: Extract cross-resource references

Call the `scan_tf_references` MCP tool with the project directory:

```
scan_tf_references(project_directory=<project path>)
```

This scans raw `.tf` files and returns:
- `edges` — cross-resource references found in HCL (high-confidence)
- `file_map` — which `.tf` file each resource is defined in
- `unresolved_references` — `var.*`, `local.*`, `module.*` references the scanner couldn't resolve
- `for_each_resources` — resources with dynamic addressing

Report the summary to user (e.g., "Scanned 12 .tf files: found 154 edges, 5 unresolved references, 3 for_each resources.")

### 3b: Review and enrich edges (optional)

Review `unresolved_references` and `for_each_resources` from the scanner output. For each unresolved reference:
- If the variable or local value is visible in the scanned files, resolve it and add the missing edge to the `edges` list
- If a `for_each` resource has references that imply specific instance addressing, expand them

This step improves clustering quality but is not blocking — proceed even if some references remain unresolved.

### 3c: Classify and cluster

Call the `cluster_terraform` MCP tool with the resource list from Step 1, the AI detection from Step 2, and the scanner output from Step 3a:

```
cluster_terraform(
  resources=<resource list from Step 1>,
  migration_dir=$MIGRATION_DIR,
  ai_detection=<result from Step 2>,
  metadata={"report_date": "<today>", "project_directory": "<project path>", "terraform_version": "<version>"},
  edges=<edges from Step 3a + any additions from Step 3b>,
  file_map=<file_map from Step 3a>
)
```

This tool performs the full pipeline deterministically:
- Excludes auth providers (Identity Platform, Firebase Auth) — these are not migrated
- Classifies resources as PRIMARY (with tier) or SECONDARY (with role)
- Builds dependency edges by merging scanner edges with `depends_on` and config references
- Resolves `serves` bidirectionally and transitively (via IAM bridge pattern)
- Computes topological depth via Kahn's algorithm
- Clusters resources by type/tier (networking cluster, same-type grouping, file proximity)
- Routes unaffiliated resources to a `shared_infrastructure` cluster
- **Writes `gcp-resource-inventory.json` and `gcp-resource-clusters.json`** to `$MIGRATION_DIR` with guaranteed correct schema

Returns:
- `summary` — counts (`total_resources`, `primary_resources`, `secondary_resources`, `excluded_resources`, `total_clusters`)
- `files_written` — list of files written to migration_dir

Report the summary to user (e.g., "Classified: 12 PRIMARY, 38 SECONDARY, 2 excluded. Generated 8 clusters.")

If any resources were excluded, report them: "Auth provider detected — excluded from migration scope. Keep your existing auth solution."

## Step 7: Verify Output and Optional AI Profile

### 7a-7c: Output files (handled by tool)

`cluster_terraform` in Step 3c already wrote `gcp-resource-inventory.json` and `gcp-resource-clusters.json` to `$MIGRATION_DIR` with guaranteed correct schema. No manual file writing or validation needed.

Confirm the tool response includes `files_written: ["gcp-resource-inventory.json", "gcp-resource-clusters.json"]`.

### 7d: Optional — Write `ai-workload-profile.json` (Vertex-strong Terraform only)

Run **only** when all of the following are true:

1. Step 2's `ai_detection.has_ai_workload` is `true`
2. **Vertex-strong:** `ai_detection.ai_services` includes `vertex_ai`

Do **not** run this step for AI signals that are **only** BigQuery ML, Document AI, Vision, etc.

**If `ai-workload-profile.json` already exists** in `$MIGRATION_DIR` with `metadata.profile_source` of `"application_code"` or `"merged"`, **skip** (do not overwrite).

**If Vertex-strong:**

1. Determine `ai_source` — examine the Vertex AI resource types:
   - If any generative-type resources exist (`google_vertex_ai_endpoint`, `google_vertex_ai_index`, `google_vertex_ai_index_endpoint`) → `ai_source = "gemini"`
   - If only traditional ML resources (`google_vertex_ai_training_pipeline`, `google_vertex_ai_custom_job`, `google_vertex_ai_batch_prediction_job`) → `ai_source = "other"`
   - If mixed, prefer `"gemini"`

2. Call the `create_ai_profile_from_iac` MCP tool:

   ```
   create_ai_profile_from_iac(
     ai_source=<"gemini" or "other">,
     ai_detection=<result from Step 2>,
     vertex_resources=<google_vertex_ai_* resources from Step 1>,
     migration_dir=$MIGRATION_DIR
   )
   ```

Report to user when written: "Wrote ai-workload-profile.json (IaC-inferred Vertex AI)."

After all steps complete, `phase_advance` handles the phase status update — do not update `.phase-status.json` here.

## Output Validation

Output files are written by `cluster_terraform` and `create_ai_profile_from_iac` tools with guaranteed correct schema. No manual validation needed — field names, structure, and cross-references are correct by construction.

---

## Design Phase Integration

The Design phase uses these outputs:

1. **From gcp-resource-clusters.json:**
   - `creation_order` — evaluates clusters depth-first (foundational first)
   - `primary_resources` / `secondary_resources` — knows which resources map independently vs which support others
   - `edges` — understands resource relationships and evidence
   - `network` — knows which VPC resources belong to
   - `dependencies` — understands cluster-level ordering
   - `must_migrate_together` — respects atomic deployment constraints

2. **From gcp-resource-inventory.json:**
   - `config` — looks up config values against design-ref signals
   - `classification` / `secondary_role` — handles primary/secondary differently
   - `serves` — determines if secondary's primary is mapped
   - `depth` — validates clustering logic
   - `tier` — routes to correct design-ref file (compute.md, database.md, etc.)
   - `ai_detection` — signals for inventory; when Step 7d ran, **`ai-workload-profile.json`** is the driver for AI Clarify/Design

3. **From `ai-workload-profile.json` (when Step 7d wrote it):** consumed in Phase 2+ per `schema-discover-ai.md` (`profile_source: "iac_vertex"`).

---

## Scope Boundary

**This phase covers Discover & Analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists in GCP. Nothing else.**
