# azure-iac-terraform — Terraform discovery oracle

A synthetic Azure estate plus a deterministic asserter. This is the **external oracle**
for `azure-to-aws` Discover over Terraform.

## Why it exists

The DSL's `_assert` postconditions cannot verify correctness. The model both produces
the artifact and evaluates the assertion against it, so a run that improvises the ARM
type vocabulary from pretraining — instead of reading
`references/shared/arm-type-canonicalization.md` — still produces well-formed output,
still satisfies every shape assertion in `discover.md`, and still emits `HANDOFF_OK`.
That output would be stamped `confidence: deterministic`, which would be false, and
two runs of the same repo would disagree with each other.

An asserter written in Python is the only thing the model cannot reason its way past.

## What the corpus is built to catch

Every block in `workspace-terraform/` exists to pin a decision where a **plausible
improvisation and the correct answer diverge**. Facts a model gets right by accident
are deliberately not asserted — they cost review attention and prove nothing.

| Corpus construct                                        | What a good improviser produces        | What the table requires                    |
| ------------------------------------------------------- | -------------------------------------- | ------------------------------------------ |
| `azurerm_linux_function_app`                            | `Microsoft.Web/functionApps`           | `Microsoft.Web/sites` + `kind`             |
| `azurerm_service_plan`                                  | `Microsoft.Web/serverFarms`            | `Microsoft.Web/serverfarms` (lowercase f)  |
| `azurerm_redis_cache`                                   | `Microsoft.Cache/redis`                | `Microsoft.Cache/Redis` (capital R)        |
| `azurerm_cosmosdb_account`                              | `Microsoft.CosmosDB/...`               | `Microsoft.DocumentDB/databaseAccounts`    |
| `azurerm_resource_group`                                | an ID with a `/providers/` segment     | no `/providers/` segment                   |
| no `subscription_id` in the provider block               | an invented GUID                       | the `<subscription-unknown>` placeholder   |
| **5 web apps on one S1 plan**                            | 5 compute line items                   | 5 `hosted_on` edges into **one** plan      |
| a plan with **zero** apps                                | omitted as uninteresting               | inventoried, 0 inbound edges, idle finding |
| app in `rg-app`, database in `rg-data`                   | edge dropped at the group boundary     | edge preserved so clustering can merge     |
| a private endpoint                                       | mapped as a target                     | skipped, but its `private_link` edge read  |
| `azurerm_dev_test_lab` (absent from the table)            | a guessed `Microsoft.DevTestLab/labs`  | reported as untranslated                   |
| a registry `module` not in the workspace                  | silence                                | a warning naming the module                |
| `enabled_protocol = "SMB"`                               | dropped                                | carried — it is the EFS-vs-FSx input       |
| `kafka_enabled = true`                                   | dropped                                | carried — it is the MSK-vs-Kinesis input   |
| `FIXTURE_SENTINEL_MUST_NOT_APPEAR` in 2 app settings + a VM password | recorded, or redacted in place | discarded entirely                |
| **5 local names reused across types** (`core`, `storefront`, `reporting`, `data`, `store`) | one entry per name, silently overwriting | one entry per full `azurerm_type.name` address |

The reused local names are deliberate and were a real bug: the first draft of this
asserter indexed on `tf_resource_name`, so five of its twenty-one type assertions were
silently pointed at the wrong resource. Identity is the full Terraform address.

The secret sentinel is a greppable token rather than a realistic-looking credential on
purpose: a realistic one would trip `gitleaks`, which runs over this repo, and a
sentinel makes the assertion unambiguous.

## Running it

The corpus is an INPUT, so there is no committed golden run tree — producing one
requires an agent run. Registered in `tools/run-asserters.py` as **smoke-only**: CI
executes it against an empty directory and requires a clean non-zero exit, which
guards against bitrot in the asserter itself.

To use it for real:

```sh
# 1. copy the corpus into a scratch workspace and run the skill's Discover phase there
cp -r workspace-terraform/. /tmp/azure-probe/ && cd /tmp/azure-probe
#    ...invoke azure-to-aws and let Discover complete...

# 2. point the asserter at the run directory it produced
python3 <this-dir>/check_expected_iac_terraform.py /tmp/azure-probe/.migration/<MMDD-HHMM>
```

A `FAIL` naming a specific canonical type is the signal that
`arm-type-canonicalization.md` was not consulted.

## Scope

Discover only, Terraform only. Discover is the right first target because its output
is a pure function of committed input — no pricing, no rubric judgment — so the
assertions can be strict rather than tolerance-based.

Not covered yet, and the corpus already contains the inputs for each: Design's
per-resource mapping and the cost-bearing-unknown STOP, the cluster merge/split, and
the Estimate reservation baseline.
