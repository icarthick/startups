# Schema — `preferences.json`

Contract for the Clarify artifact. `clarify-assemble.md` is its single creator.

## Disposition vocabulary

Every row carries one of four dispositions, and the distinction is load-bearing:

| Disposition | Meaning                                                                      |
| ----------- | ---------------------------------------------------------------------------- |
| `DETECTED`  | read from the estate; shown for confirmation, not asked                       |
| `PROPOSED`  | the skill's recommendation with a default the user may change                  |
| `ESSENTIAL` | cannot be defaulted; the phase does not complete until it is answered          |
| `N/A`       | considered and does not apply to this estate                                   |

`N/A` is written explicitly, never omitted. An absent key and a considered `N/A` are
different facts, and the report distinguishes them — "we checked your estate for SQL
licensing exposure and found none" is a different statement from silence.

## Shape

```jsonc
{
  "phase": "clarify",
  "global": {
    "target_region": { "disposition": "PROPOSED", "value": "us-east-1", "default": "us-east-1" },
    "migration_window": { "disposition": "PROPOSED", "value": null, "default": null },
    "environment_scope": { "disposition": "DETECTED", "value": [], "default": [] }
  },
  "design_constraints": {
    "cpu_architecture": { "disposition": "PROPOSED", "value": "x86_64", "default": "x86_64" },
    "compute_target": { "disposition": "PROPOSED", "value": null, "default": "elastic_beanstalk" },
    "cost_optimization": { "disposition": "PROPOSED", "value": null, "default": "balanced" }
  },
  "data": {},
  "identity": { "disposition": "PROPOSED", "value": "identity_center_reinvite", "default": "identity_center_reinvite" },
  "licensing": { "disposition": "N/A", "value": null, "default": null },
  "app_service_plans": [
    { "plan_azure_id": "<azure_id>", "isolation_split": { "disposition": "PROPOSED", "value": false, "default": false } }
  ],
  "clusters": [
    { "cluster_id": "<slug>", "pattern_id": { "disposition": "DETECTED", "value": "unclassified", "default": "unclassified" } }
  ],
  "workshop": {}
}
```

Notes on the non-obvious defaults:

- **`cpu_architecture` defaults to `x86_64`**, which diverges from the repo-wide
  Graviton default on purpose. See SKILL.md § Philosophy.
- **`identity` always has a row** (the identity category always fires), defaulting to
  a fresh IAM Identity Center re-invite rather than full Entra ID federation.
- **`isolation_split` defaults to `false`.** A split is only ever a stated isolation
  requirement, because splitting multiplies compute cost.

## Status — skeleton (build step 1)

The disposition vocabulary and the shape are the real contract. The per-category
question sets that populate `data`, `licensing`, and the AI keys land in step 5.
