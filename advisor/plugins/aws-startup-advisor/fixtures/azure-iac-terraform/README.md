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

## Layout

| Path                                | Role                                                                 |
| ----------------------------------- | -------------------------------------------------------------------- |
| `workspace-terraform/`              | the committed INPUT — 28 resources + 1 unresolvable module           |
| `expected-iac-terraform.json`       | pinned Discover facts                                                |
| `check_expected_iac_terraform.py`   | the Discover oracle                                                  |
| `after-discover/`                   | GOLDEN Discover output — 27 resources                                |
| `expected-design.json`              | pinned Design pass-1 facts                                           |
| `check_expected_design.py`          | the Design oracle                                                    |
| `after-design-halted/`              | GOLDEN Design output — a **halted** design, see below                |

Both asserters are registered in `tools/run-asserters.py` as **golden**: CI runs each
against its committed tree and requires exit 0.

## Running it

```sh
# 1. copy the corpus into a scratch workspace and run the skill there
cp -r workspace-terraform/. /tmp/azure-probe/ && cd /tmp/azure-probe
#    ...invoke azure-to-aws and let Discover (then Design) run...

# 2. point each asserter at the run directory it produced
python3 <this-dir>/check_expected_iac_terraform.py /tmp/azure-probe/.migration/<MMDD-HHMM>
python3 <this-dir>/check_expected_design.py        /tmp/azure-probe/.migration/<MMDD-HHMM>
```

A `FAIL` naming a specific canonical type is the signal that
`arm-type-canonicalization.md` was not consulted. A `FAIL` naming DynamoDB, EFS, or
Kinesis is the signal that `knowledge/design/fast-path-services.json` was not.

## The Design oracle

`after-design-halted/aws-design.json` is a **halted** design, and the directory name
says so. Two things block it, both deliberately:

1. the corpus carries an **untranslated** cost-bearing type (`azurerm_dev_test_lab`),
   which STOPs the design — the skill could not name the resource, so it cannot show
   the resource is free;
2. the pass-2 category rubric files (`compute.md`, `database.md`) do not exist yet
   (build step 5), so every compute and relational-database resource lands in
   `pending_rubric[]` rather than being mapped from model priors.

So the tree does **not** satisfy `design.md`'s `_postconditions`, and it is not
supposed to. What it pins is the **table's application**, which is what build step 3
delivers. `clusters[]` is absent for the same reason: cluster-level fields land in
build step 4, and fabricating them here would put unverifiable data in a committed
golden tree.

The Design asserter additionally validates the **table itself** —
`knowledge/design/fast-path-services.json` — for its required rows, the
precedence invariant (a canonical type resolves to at most one disposition), and the
App Runner ban. A design is only as trustworthy as the rows it claims to have read,
and the `deterministic` label is checked in **both** directions: every expected row
carries it, and every entry carrying it names a type that really is in the table with
a target that row allows. The second direction is what catches an improvised label.

Three rows exist because a single mechanical discriminator fully determines the
target, so there is no rubric left to run — and each has a famous wrong answer that a
capable improviser reaches for:

| Corpus construct                             | The improviser's answer | The table's answer          |
| -------------------------------------------- | ----------------------- | --------------------------- |
| Cosmos account, `kind: MongoDB`              | DynamoDB                | **DocumentDB**              |
| storage share, `enabled_protocol = "SMB"`    | EFS                     | **FSx for Windows File Server** |
| Event Hubs namespace, `kafka_enabled = true` | Kinesis                 | **MSK**                     |

## Scope

Terraform only, and Discover + Design pass 1 only. Both are pure functions of
committed input — no pricing, no rubric judgment — so the assertions can be strict
rather than tolerance-based.

**Not covered, and honestly so:**

- **The specialist gates.** The corpus contains no Managed Instance, elastic pool,
  Synapse workspace, Data Factory, or SQL-Server VM image, so no gate fires and the
  five gate rows are reviewed rather than verified. A gate fixture belongs with build
  step 5, when `database.md` exists to be the thing a gate is chosen *instead of*.
- **The `accounting` check is redundant on this corpus.** All 27 resources are already
  covered by a more specific assertion (9 deterministic + 5 pending + 7 skips + 6
  consumed apps), so it cannot fail alone here. It is kept because it is the check
  that survives a corpus change.
- **The cluster merge/split** (build step 4) and the **Estimate reservation baseline**.
  The corpus already contains the inputs for both.

## Both trees, and how the asserter stays identical

`check_expected_design.py` reaches the mapping table at
`../../skills/azure-to-aws/knowledge/design/fast-path-services.json`, a path that
resolves the same way in the `advisor/` and `migrate/` plugin trees. That is what lets
the two copies stay byte-identical under `drift:check`.
