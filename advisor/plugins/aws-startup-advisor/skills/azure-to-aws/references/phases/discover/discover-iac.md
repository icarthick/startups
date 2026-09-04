---
_fragment: iac
_of_phase: discover
_contributes:
  - azure-resource-inventory.json (resources[], iac_metadata section)
---

# Discover — Infrastructure as Code

> **Fragment unit.** One of the discover phase's independent discoverers. See
> `discover.md` for how it is composed into the phase.

## Why one fragment covers three dialects

Terraform `azurerm_*`, Bicep, and ARM JSON all land here. Bicep compiles *to* ARM
and both key off the same `Microsoft.*` type namespace, so they share one reason to
change; all three converge on one section of one artifact; and the extraction
semantics (Azure resource type → inventory entry) are shared, with only the surface
syntax differing.

Its trigger is `{ _always: true }`, not a `_glob`. No single glob spans `.tf`,
`.bicep`, and ARM templates — ARM is plain `.json`, identifiable only by a `$schema`
containing `deploymentTemplate`. A `_when` would fail open: one misjudgment silently
drops all IaC discovery. So this fragment always runs, detects the dialects present
itself, and exits cleanly when it finds none.

## Provenance is per dialect

Because this fragment always runs and may exit empty, "the fragment ran" proves
nothing. Record in `metadata.discovery_sources` only the dialects that actually
produced at least one resource, and set `source` on each resource entry to the
dialect it came from. The phase's `_postconditions` assert per dialect: if `.tf` /
`.bicep` / ARM files were found in the workspace, at least one resource must be
sourced from each dialect that was found.

## Status — skeleton (build step 1)

Terraform (`azurerm_*`) extraction only, and the `azurerm_* → Microsoft.*`
translation table it needs is not written yet.

| Lands in | What                                                                                                              |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| step 2   | Bicep and ARM extraction, via `references/shared/extract-{terraform,bicep,arm}.md` loaded only for dialects present |
| step 3   | `references/shared/arm-type-canonicalization.md` — the `azurerm_* → Microsoft.*` table applied here                |

Keeping the extraction rules in separate `extract-*.md` refs is a context-budget
decision, not a taste one: gcp's single-dialect `discover-iac.md` is already 402
lines, and this phase also loads the app-code, billing, RDfA, and live fragments.

## Step: Extract

1. Detect which dialects are present. If none, write nothing, add no discovery
   source, and exit cleanly — this is a normal outcome, not an error.
2. For each dialect present, load its `extract-*.md` ref and follow it.
3. Translate every extracted type to its canonical `Microsoft.*` form. Reconstruct
   `azure_id` for Terraform-sourced resources (the other dialects supply it).
4. Append to `azure-resource-inventory.json`'s `resources[]` and write the
   `iac_metadata` section. Never emit a secret value; app settings and connection
   strings carry names only.
