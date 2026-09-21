# Azure Terraform basic fixture

Golden Discover output for a simple Azure workload: one Linux web app on P1v2 service plan,
a PostgreSQL Flexible Server, a Storage Account, and a Key Vault — all in one resource group.

Tests the `azure-to-aws` Discover phase: flat inventory, no clustering, correct resource IDs,
no secret values leaked, discovery_sources = ["terraform"].

| Path                         | Role                                                                                     |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| `seed/`                      | Cold-start workspace: `.phase-status.json` (all pending) + `main.tf` (azurerm resources) |
| `after-discover/`            | Golden Discover output: `azure-resource-inventory.json` + updated `.phase-status.json`   |
| `expected-discover.json`     | Assertions for the asserter                                                              |
| `check_expected_discover.py` | Stdlib checker (run as GOLDEN by `mise run fixtures:assert`)                             |

## Assert a run

```bash
python3 check_expected_discover.py after-discover
# or against a live run dir that completed Discover from seed/:
python3 check_expected_discover.py /path/to/.migration/MMDD-HHMM
```

## Fresh-agent replay bar

Copy `seed/*` into a scratch `.migration/<id>/` directory (including `.phase-status.json`
with `discover: pending`), invoke the azure-to-aws skill with `seed/main.tf` as the
workspace, let Discover run, then `python3 check_expected_discover.py <scratch_dir>` —
must **PASS**. The committed `after-discover/` is the reference snapshot.
