# Render Pricing Cache

<!-- Last updated: 2026-09-19 -->
<!-- Source: https://render.com/pricing -->
<!-- Verification: manually reviewed render.com/pricing page as of 2026-09-19 -->
<!-- Staleness window: 90 days (see pricing:staleness gate) -->

> **IMPORTANT — USE AS BASELINE ONLY:** This cache captures Render's _listed_
> monthly plan prices at the Last-updated date above. Use these as the
> **source-side baseline** in cost comparisons. Never present these as the
> authoritative current price — direct users to https://render.com/pricing for
> current pricing. The `pricing:staleness` CI gate warns when this file is older
> than its staleness window.

---

## Web Services

| Plan      | vCPU | RAM    | $/month (USD) |
| --------- | ---- | ------ | ------------- |
| Free      | 0.1  | 512 MB | $0 (limited)  |
| Starter   | 0.5  | 512 MB | $7            |
| Standard  | 1    | 2 GB   | $25           |
| Pro       | 2    | 4 GB   | $85           |
| Pro Plus  | 4    | 8 GB   | $175          |
| Pro Max   | 8    | 16 GB  | $325          |
| Pro Ultra | 16   | 32 GB  | $625          |

Notes:

- Free tier is subject to spin-down after 15 minutes of inactivity; billed per-second when active with limited free hours per month
- Prices are per-instance; multiple instances multiply accordingly
- Additional bandwidth billed at $0.10/GB after free tier

---

## Background Workers

| Plan      | vCPU | RAM    | $/month (USD) |
| --------- | ---- | ------ | ------------- |
| Free      | 0.1  | 512 MB | $0 (limited)  |
| Starter   | 0.5  | 512 MB | $7            |
| Standard  | 1    | 2 GB   | $25           |
| Pro       | 2    | 4 GB   | $85           |
| Pro Plus  | 4    | 8 GB   | $175          |
| Pro Max   | 8    | 16 GB  | $325          |
| Pro Ultra | 16   | 32 GB  | $625          |

Notes: Same pricing tiers as Web Services. Background Workers don't expose HTTP endpoints.

---

## Cron Jobs

| Plan     | vCPU | RAM    | $/month (USD)        |
| -------- | ---- | ------ | -------------------- |
| Free     | 0.1  | 512 MB | $0 (1 cron per acct) |
| Starter  | 0.5  | 512 MB | $1 (first, then +$1) |
| Standard | 1    | 2 GB   | $5                   |
| Pro      | 2    | 4 GB   | $18                  |
| Pro Plus | 4    | 8 GB   | $38                  |

Notes:

- Cron jobs are billed per-job per-month at the above rates
- Exact per-invocation pricing when using per-second billing model varies
- **Unverified** — the precise per-job monthly pricing model vs per-invocation billing varies by plan; verify at https://render.com/pricing before using in comparisons

---

## PostgreSQL (Managed Databases)

| Plan     | RAM    | Storage | $/month (USD)     |
| -------- | ------ | ------- | ----------------- |
| Free     | 256 MB | 1 GB    | $0 (90-day limit) |
| Starter  | 1 GB   | 10 GB   | $7                |
| Standard | 4 GB   | 100 GB  | $85               |
| Pro      | 8 GB   | 512 GB  | $175              |
| Pro Plus | 16 GB  | 1 TB    | $325              |

Notes:

- Free PostgreSQL instances expire after 90 days
- Backup retention: 7 days on Starter, 30 days on Standard+
- High Availability (multi-region, automatic failover) available on Standard+ as an add-on
- Read replicas available on Standard+ at additional cost

---

## Key Value (Redis)

| Plan     | RAM    | $/month (USD) |
| -------- | ------ | ------------- |
| Free     | 25 MB  | $0 (limited)  |
| Starter  | 50 MB  | $3            |
| Standard | 500 MB | $25           |
| Pro      | 2 GB   | $55           |
| Pro Plus | 5 GB   | $115          |

Notes:

- Persistence (RDB/AOF) available on Standard+
- Eviction policies configurable on Standard+
- **Unverified** — Key Value pricing was recently rebranded from "Redis" to "Key Value"; verify current plan names and prices at https://render.com/pricing

---

## Static Sites

| Plan      | $/month (USD) |
| --------- | ------------- |
| All plans | $0 (free)     |

Notes: Static sites are free on Render. Out of scope for render-to-aws v1 (see SKILL.md).

---

## Private Services

| Plan     | vCPU | RAM    | $/month (USD) |
| -------- | ---- | ------ | ------------- |
| Starter  | 0.5  | 512 MB | $7            |
| Standard | 1    | 2 GB   | $25           |

Notes: Private Services are internal HTTP services not exposed externally. Out of scope for render-to-aws v1.

---

## Bandwidth

| Tier         | $/GB (USD) |
| ------------ | ---------- |
| First 100 GB | $0 (free)  |
| After 100 GB | $0.10/GB   |

---

## Notes on Pricing Uncertainty

The following entries are **marked unverified** because the exact current pricing
could not be confirmed at the cache-update date and may have changed:

- Cron Job per-job pricing model (see Cron Jobs section)
- Key Value plan names and RAM tiers (recently rebranded)

Use https://render.com/pricing as the authoritative source. If pricing is stale,
run `mise run pricing:staleness` and update this file from the current vendor page.
