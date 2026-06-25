# Lightweight Billing Extraction

> Loaded when Terraform is the primary source and billing files also exist.
> Extracts service-level costs and AI signals without full billing analysis.

## Step 1: Identify Billing File

Locate the billing file in the project directory (first match from: `*billing*.csv`, `*billing*.json`, `*cost*.csv`, `*cost*.json`, `*usage*.csv`, `*usage*.json`).

## Step 2: Extract Summary

Call the `extract_billing_summary` MCP tool:

```
extract_billing_summary(billing_file=<path to billing file>, output_dir=<$MIGRATION_DIR>)
```

This produces `billing-profile.json` in `$MIGRATION_DIR` with service-level costs and AI signal detection.

## Step 3: Report

If the tool returns `ai_signals_detected: true`, note this for the Clarify phase (AI-related questions will be triggered).

Output: "Billing data extracted: $X/month across N services. AI signals: [detected/not detected]."
