# Real-Repo End-to-End Run — VERDICT

**What:** Ran the full DSL skill (discover → clarify[all-defaults] → design →
estimate → generate, STOP before feedback) against a REAL Heroku terraform repo
(`SawsMigrate-SampleData/.../large-terraform`): 3 apps (one Fir-stack), 6
formations (incl. a `clock` process + performance-m), 5 addons (2 postgres, 2
redis, 1 kafka), a Private Space (no peering), a pipeline (2 couplings), 5
domains. Cold LLM, zero context, read-only (computed each phase's artifacts to
feed the next).

## Result: PASS end-to-end — every phase HANDOFF_OK, no GATE_FAIL

The chain ran clean discover→generate with all-defaults; no phase blocked or
reverted. The subtle real-repo branches all resolved correctly:

- **Private Space WITHOUT peering** → `new_vpc` + restricted SGs + Q9/Q9b
  skipped-not-applicable (not blocked on the no-default subnet/VPC questions).
- **Fir app** (frontend, stack `fir`) → mapped to Fargate normally + a detect-only
  `fir_workloads_detected` note; NO ARM/Graviton/CNB leak.
- **`clock` process type** → Fargate (standard-1x → 256/512), no ALB.
- Fast-path correctly ineligible (space + kafka); multi-AZ conventions correct
  (ElastiCache ×2; RDS baked-in / MSK intrinsic NOT doubled); pipeline → warning;
  13 services, complexity = large (service_count ≥ 9).

## The defect this caught (real, ship-blocking — FIXED)

Running against REAL data (not toy fixtures) surfaced a **cross-table coverage
gap the unit cold-tests missed**: the design RDS table
(`postgres-rds-sizing.json`) emits `db.m6g.*` / `db.r6g.16xlarge` /
`db.x2g.16xlarge` instance classes for every production Postgres tier
(≥ standard-2), but the estimate rate table (`aws-pricing.json.rds_postgresql`)
only had `db.t4g.*`. So BOTH real Postgres instances (standard-4 → m6g.2xlarge,
standard-2 → m6g.large) priced as **`unpriced`** → silently excluded from the
balanced total. The estimate still passed Property-16 (excluding unpriced lines
is legitimate), so no gate caught it — but the cost picture was materially
understated (a standard-4 RDS is ~$1k+/mo, the dominant line). Aurora was
fully covered, so the gap was RDS-specific.

**Fix:** added Multi-AZ RDS rates for every m6g/r6g/x2g class the design table can
emit (full coverage verified: design RDS classes ⊆ estimate RDS rates). Audited
the other tables (redis/kafka/aurora nodes, EKS nodes) — RDS was the ONLY gap.
Also removed a duplicated NAT bullet in `estimate-cost-engine.md` (a copy-paste
from the EKS edit; could invite a NAT double-count).

## Lesson

Toy fixtures used `db.t4g.medium` (the one class both tables shared), so the
gap never showed. A real repo with production-sized plans exposed it
immediately. The structural gates (schema, Property-16, route gates) are sound
but cannot catch a design service that legitimately prices as `unpriced` — a
**knowledge-data consistency** check (every instance class a design table can
emit must have a rate) is the missing CI conformance item. Worth adding to the
taxonomy conformance checklist.

## Net

The DSL skill runs a real, complex, multi-app Heroku repo end-to-end with
all-defaults and produces a complete artifact set. One real knowledge-data
defect (RDS rate coverage) found + fixed; the DSL/gates behaved correctly
throughout. This is the strongest validation yet — a genuine repo, not a crafted
fixture.
