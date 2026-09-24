# azure-iac-bicep — Bicep discovery oracle

A synthetic Azure estate plus a deterministic asserter. This is the **external
oracle** for `azure-to-aws` Discover over Bicep.

## Why it exists

The DSL's `_assert` postconditions cannot verify correctness — the model both
produces the artifact and evaluates the assertion, so a run that improvises Bicep
semantics from pretraining instead of reading
`references/shared/extract-bicep.md` still produces well-formed output, still
satisfies every shape assertion, and still emits `HANDOFF_OK`. An asserter
written in Python is the only thing the model cannot reason its way past.

## What the corpus is built to catch

Only the Bicep-specific divergences not already covered by the Terraform fixture.
The ARM type vocabulary, edge semantics, and secret boundary are already pinned
there; this fixture pins the parts that differ because the IaC dialect differs.

| Corpus construct                                           | Wrong answer                            | Right answer                                                                           |
| ---------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------- |
| `'Microsoft.Storage/storageAccounts@2021-06-01'`           | `azure_type` includes `@2021-06-01`     | stripped to `Microsoft.Storage/storageAccounts`; version in `config.bicep_api_version` |
| `source:` field                                            | `"terraform"`                           | `"bicep"` on every entry                                                               |
| `resource kv '…' existing = {…}`                           | omitted (not deployed by this template) | inventoried with `config.bicep_existing: true`                                         |
| `resource ws '…' = [for i in range(0, 3): {…}]`            | three separate inventory entries        | one entry with `config.multiplicity_unresolved: true`                                  |
| local module `./modules/web.bicep`                         | module's resource silently absent       | discovered with `config.bicep_module: 'module.webMod'`                                 |
| registry module `br/public:…` not on disk                  | silence                                 | `module_not_resolved` warning naming the module                                        |
| `serverFarmId: appServicePlan.id`                          | no edge, or wrong `to`                  | `hosted_on` edge resolving to the plan's `azure_id`                                    |
| `FIXTURE_SENTINEL_MUST_NOT_APPEAR` as an app-setting value | recorded or redacted                    | discarded entirely; key appears in `app_setting_names`                                 |

The sentinel is a greppable token rather than a realistic credential to avoid
tripping `gitleaks`, which scans this repo.

## Layout

| Path                                | Role                                                                                                                                |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `workspace-bicep/main.bicep`        | committed INPUT — 6 resources (5 root + 1 from local module), 1 loop resource, 1 `existing` resource, 1 registry module not on disk |
| `workspace-bicep/modules/web.bicep` | local module — its resource must be discovered with `bicep_module` provenance                                                       |
| `expected-iac-bicep.json`           | pinned Discover facts                                                                                                               |
| `check_expected_iac_bicep.py`       | the Discover oracle                                                                                                                 |
| `after-discover/`                   | GOLDEN Discover output — 6 resources                                                                                                |

The asserter is registered in `tools/run-asserters.py` as **golden**: CI runs it
against the committed `after-discover/` tree and requires exit 0.

## Running it

```sh
# 1. copy the corpus into a scratch workspace and run the skill there
cp -r workspace-bicep/. /tmp/azure-bicep-probe/ && cd /tmp/azure-bicep-probe
#    ...invoke azure-to-aws and let Discover run...

# 2. point the asserter at the run directory it produced
python3 <this-dir>/check_expected_iac_bicep.py /tmp/azure-bicep-probe/.migration/<MMDD-HHMM>
```
