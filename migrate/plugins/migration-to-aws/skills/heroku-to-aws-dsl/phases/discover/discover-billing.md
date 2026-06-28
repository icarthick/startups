---
_fragment: billing
_of_phase: discover
_scope: >
  Parse Heroku billing/invoice exports into a structured billing profile. ONLY
  this — no AWS service names, no AWS cost projections, no Heroku-vs-AWS
  comparison (that is the estimate phase). Optional; NEVER fails the phase.
  Does NOT update `.phase-status.json`.
_produces: [billing-profile.json]
_postconditions:
  - { _assert: "billing-profile.json is valid JSON with an 'available' boolean", _on_failure: _warn_and_skip }
  - { _assert: "if available==true -> total_monthly_cost is a number AND line_items[] present", _on_failure: _warn_and_skip }
_on_error:
  _warn_and_skip: { effect: "record parse_warning; skip file/row; continue", status: continue }
---

# Discover Fragment: Billing (optional)

> A discover-phase FRAGMENT, INDEPENDENT of the terraform fragment (it never
> reads terraform's output — no inter-fragment dependency). Triggered ONLY when a
> billing/invoice file matches the phase's glob trigger. Single responsibility:
> parse billing data. WRITES `billing-profile.json`; the assembler later merges
> that into `heroku-resource-inventory.json` as the `billing_profile` section.
> Billing is OPTIONAL and must NEVER fail the phase — any parse failure warns and
> skips. Does NOT update `.phase-status.json`.

## Step: detect_billing_format

```meta
_collect: [parse_warnings]
_writes_var: billing_files_parsed
```

For each billing file found by the trigger glob, determine the format by
inspection.

**CSV (read the header row):**

| Header contains                                          | `source_format`  |
| -------------------------------------------------------- | ---------------- |
| `app`, `dyno_units`, `addon_total`, `platform_total`     | `enterprise_csv` |
| `description`, `amount`, `period_start`, `period_end`    | `invoice_csv`    |
| `resource_name`, `category`, `cost`                      | `line_item_csv`  |

**JSON (parse and check top-level shape):**

| Structure                                                  | `source_format`    |
| ---------------------------------------------------------- | ------------------ |
| `total`, `period_start`, `period_end`, `charges[]`         | `invoice_json`     |
| `invoice_id`, `total_amount`, `line_items[]`               | `api_invoice_json` |
| `apps[]` with nested cost objects                          | `enterprise_json`  |

Unrecognized header/structure, or malformed JSON → record a `parse_warning`
naming the file, **skip it** (`_warn_and_skip`), try the next billing file. If
none remain recognized, contribute `billing_profile = {available:false}`.

## Step: parse_line_items

```meta
_collect: [parse_warnings]
_writes_var: line_items
```

Normalize each recognized file into line items `{resource_name, category, cost}`
where `category ∈ {dyno, addon, platform, other}`.

- **enterprise_csv**: `app`→`resource_name`; `period`→`billing_period` (YYYY-MM).
  The line-item COST is always the dollar-amount column, NEVER a count column:
  use `dyno_cost` (fall back to `dyno_units` ONLY if no `dyno_cost` exists)→dyno;
  `addon_total`/`addon_cost`→addon; `platform_total`/`platform_cost`→platform.
  A `total` column is the row total (used for the cross-check below), NOT a line
  item — do not emit it as one.
- **invoice_csv / invoice_json / api_invoice_json**: parse the `description`
  text → `resource_name` + `category`:
  - "Dyno usage for {app}" → `{app}`, `dyno`
  - "Add-on: {addon} for {app}" / "{addon} ({app})" → `{app}`, `addon`
  - "Platform" / "SSL" / "Support" → `platform`, `platform`
  - otherwise → `unknown`, `other`
  - `amount`→`cost`; `currency` if present else `"USD"`; period from
    `period_start`. For `api_invoice_json`, a `line_items[].app_name` field
    overrides description parsing.
- **enterprise_json**: iterate `apps[]` → per-app dyno/addon/platform line items;
  period from top-level metadata or filename (YYYY-MM).

Row/item missing required fields → warn, skip the row, continue.

## Step: build_billing_profile

```meta
_writes: billing-profile.json
_collect: [parse_warnings]
```

1. `total_monthly_cost` = sum of all line-item costs (authoritative).
2. `billing_period` (YYYY-MM), `currency` (default `"USD"`), `available:true`.
3. Per-app breakdown: group by `resource_name`, sum per category, omit $0 lines.
4. Cross-check: if a file-reported total differs from the line-item sum by
   > $0.01, warn and use the line-item sum.
5. **Multiple files**: use the most recent `billing_period`; same period →
   prefer enterprise format (richer per-app breakdown); log the chosen file.

WRITE `billing-profile.json` to `$MIGRATION_DIR/` (the `billing_profile` object;
the assembler folds it into the inventory as the `billing_profile` section):

```json
{
  "available": true,
  "total_monthly_cost": 450.0,
  "currency": "USD",
  "billing_period": "2026-02",
  "source_file": "billing-export-2026-02.csv",
  "source_format": "enterprise_csv",
  "line_items": [
    { "resource_name": "my-web-app", "category": "dyno", "cost": 100.0 },
    { "resource_name": "my-web-app", "category": "addon", "cost": 200.0 },
    { "resource_name": "my-web-app", "category": "platform", "cost": 50.0 }
  ],
  "parse_warnings": []
}
```

## Output

This fragment WRITES `billing-profile.json`. The assembler reads it and folds it
into `heroku-resource-inventory.json` as the `billing_profile` section, adding
`"billing"` to `metadata.discovery_sources`. If this fragment is skipped (no
billing files) or all files fail to parse, no `billing-profile.json` is written
and the assembler uses `billing_profile = {available:false}`.

## Scope

Parse Heroku billing data into a structured profile. Nothing else — no AWS
service names, no AWS cost projections, no Heroku-vs-AWS comparison (that is the
estimate phase). Do NOT update `.phase-status.json` from here.
