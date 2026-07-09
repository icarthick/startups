---
_assemble: assemble-discovery
_of_phase: discover
_reads:
  - iac (fragment contribution)
  - app-code (fragment contribution)
  - billing (fragment contribution)
_produces:
  - { file: ai-workload-profile.json, _when: "app-code discovery reached >= 70% confidence, and/or discover-iac made a Vertex-strong inference" }
  - migration-preview.json
---

# Discover — Assemble Discovery Outputs

> **Assembler unit.** Runs after the discover fragments (`discover-iac.md`,
> `discover-app-code.md`, `discover-billing.md`) have produced their contributions.
> It owns two cross-cutting artifacts: the **merged** `ai-workload-profile.json` and
> the derived `migration-preview.json`. See `discover.md` for how this unit is
> composed into the phase.
>
> The per-route primary artifacts (`gcp-resource-inventory.json`,
> `gcp-resource-clusters.json`, `billing-profile.json`) are written directly by their
> creating fragments; this assembler does not re-create them. Its job is the two
> artifacts that depend on **more than one** fragment (the AI profile can be sourced
> from BOTH app-code and IaC) or on **all** of them (the preview).

**Execute ALL steps in order. Do not skip or deviate.**

## Step 1: Merge the AI workload profile (single creator)

`ai-workload-profile.json` can be sourced two ways, and both may fire in one run:

- **App code** (`discover-app-code.md`) — when overall AI confidence >= 70%, it emits
  a full profile with `metadata.profile_source: "app_code"`.
- **IaC Vertex-strong inference** (`discover-iac.md` Step 7d) — when Terraform shows
  strong Vertex AI signal, it emits a profile with
  `metadata.profile_source: "iac_vertex"`.

This assembler is the **single creator** of the final `ai-workload-profile.json`.
Reconcile the fragment contributions into one artifact:

1. If **only one** source contributed → write that profile unchanged (it already
   carries the correct `metadata.profile_source`).
2. If **both** contributed → merge them: union the detected `models[]` (dedupe by
   `model_id`), OR the boolean capability flags in `integration.capabilities_summary`,
   take the higher `summary.confidence`, and set `metadata.profile_source: "both"`.
   Prefer app-code values for `integration.pattern` and `integration.primary_sdk`
   (direct code evidence outranks billing/IaC inference); note any conflict in
   `metadata.merge_notes`.
3. If **neither** contributed → do not write the file. AI is simply absent from this
   migration; that is a valid outcome (infra-only or billing-only run).

Validate the merged artifact against `schemas/ai-workload-profile.schema.json`.

## Step 2: Compute the migration preview

Load `references/discover/discover-preview.md` and follow it to compute the
migration preview from whatever discovery artifacts exist. It writes
`migration-preview.json` (always written when any discovery artifact exists) and the
preview chat block surfaced in the completion message. `migration-preview.json` must
have `complexity_signal` set.

## Step 3: Artifact-level contract (this phase's completion shape)

The phase's `_postconditions` enforce the contract this assembler is responsible for:

- At least one discovery artifact exists (`gcp-resource-inventory.json`,
  `ai-workload-profile.json`, or `billing-profile.json`). If none, the phase must not
  complete — surface: "Discovery ran but produced no artifacts. Check that your input
  files contain valid GCP resources and try again."
- Every triggered route produced its required artifact(s) (the route output gate):
  IaC → inventory + clusters; billing (full or lightweight) → billing profile;
  app-code past its confidence gate → AI profile.
- `migration-preview.json` exists with `complexity_signal` set.

Do NOT modify any artifact to force a gate pass. On any failure the interpreter emits
`GATE_FAIL` and stops without advancing (`INTERPRETER.md` § Gate protocol).
