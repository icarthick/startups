---
_assemble: assemble-generation
_of_phase: generate
_reads:
  - artifacts-infra (fragment contribution)
  - artifacts-docs (fragment contribution)
  - artifacts-report (fragment contribution)
_produces:
  - generation-warnings.json
---

# Generate — Assemble and Account

> **Assembler unit.** The single creator of `generation-warnings.json`. The
> artifact-emitting fragments create their own files; this unit's job is to prove
> nothing was dropped. See `generate.md` for how it is composed into the phase.

**Execute the steps in order. This is the phase's accounting gate.**

## Step 1: Account for every designed service

Walk `aws-design.json` `services[]`. Each entry must be in exactly one of these states,
and the state must be demonstrable:

- **Generated** — a resource for it exists in an emitted `.tf` file. (A service folded by
  the App Service Plan fan-in is "generated" via its plan's single compute target — record
  it as folded, not dropped.)
- **Intentionally not generated** — a skip (config source / observability) or a `deferred[]`
  specialist item. This MUST have a `generation-warnings.json` entry saying why.

Any service that is neither generated nor warned is a **dropped resource** — a gate
failure, not a warning.

## Step 2: Carry deferrals

For every `aws-design.json` `deferred[]` entry, write a `generation-warnings.json` entry
with its reason and recommendation, so a specialist deferral is visible in the output and
not only in the design.

## Step 3: Scans (gate failures, not warnings)

Scan the emitted `.tf` files:

1. **Placeholder scan** — any leftover `{{VARIABLE}}` token is a gate failure. User-supplied
   values belong in `variables.tf` as `var.*` references (with validation blocks).
2. **Secret-value scan** — no secret VALUE from `azure-resource-inventory.json` may appear in
   any generated artifact. Secrets are emitted as Secrets Manager references only. A hit is a
   gate failure. (Match against the inventory's captured secret values / Key Vault secret
   contents; note discovery never captured Key Vault secret *values*, so this guards against
   any that leaked via app-settings.)

On any gate failure: emit `GATE_FAIL`, do not mark the phase complete, do not patch the
artifact to force a pass.

## Step 4: Do not overwrite inputs

Emit only `generation-warnings.json` (and the fragments' own files). Never write a phase
input — `generate.md`'s `_forbids_files` names the state artifacts explicitly.

## generation-warnings.json shape

```json
{
  "phase": "generate",
  "accounted": <int>,
  "generated": <int>,
  "deferred": [ { "azure_id": "...", "azure_type": "...", "reason": "...", "recommendation": "..." } ],
  "skipped": [ { "azure_id": "...", "reason": "config_source|observability|folded_into_plan", "detail": "..." } ],
  "warnings": [ { "code": "...", "subject": "...", "detail": "..." } ]
}
```

Every `services[]` entry is reflected in `generated` count, `deferred[]`, or `skipped[]` —
the sum accounts for all of them.

## Step 5: Report

Report to the parent orchestrator (`generate.md` owns the phase-status update and the
final `HANDOFF_OK`). Do not update `.phase-status.json` here.

## Status — implemented (build step: Generate)

Accounting + scans implemented: per-service accounting (generated / deferred / skipped /
folded), deferral carry-through, placeholder + secret-value scans as gate failures, and
the `generation-warnings.json` shape. Mirrors the discipline of gcp-to-aws's generate
completion gate while owning azure's fan-in "folded" state explicitly.
