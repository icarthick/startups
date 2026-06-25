# Discover Phase: Billing Discovery

> Self-contained billing discovery sub-file. Scans for billing CSV/JSON files, parses billing data, builds service usage profiles, flags AI signals, and generates `billing-profile.json`.
> If no billing files are found, exits cleanly with no output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Extract Billing Summary

Call the `extract_billing_summary` MCP tool:

```
extract_billing_summary(project_dir=<project root>, output_dir=<$MIGRATION_DIR>)
```

This tool performs the full billing pipeline:
1. Scans for billing files (`*billing*.csv`, `*cost*.json`, etc.)
2. Parses GCP billing export CSV or BigQuery JSON
3. Separates CUD commitment fee rows from service usage
4. Aggregates service-level costs (sorted by spend descending)
5. Extracts discount credits (committed usage, sustained usage, free tier)
6. Flags AI signals (Vertex AI, Generative AI, BigQuery ML, specialized AI)
7. Writes `billing-profile.json` to `$MIGRATION_DIR`

If the tool returns `status: "skipped"`, no billing files were found — **exit cleanly**. Other sub-discovery files may still produce artifacts.

---

## Step 2: Validate

Call `validate_discovery` to check the output:

```
validate_discovery(artifact_type="billing", content=<billing-profile.json content>)
```

---

## Step 3: Report

Summarize what was extracted:
- Total monthly spend and service count
- Whether CUD commitments were detected (and effective discount %)
- Whether AI signals were detected (triggers AI questions in Clarify phase)

After generating the output file, `phase_advance` handles the phase status update — do not update `.phase-status.json` here.

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
