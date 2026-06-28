# Estimate Arithmetic Probe — FINDING (pre-authoring)

**Why this probe:** estimate is the genuinely-untested arithmetic fork. Design's
"math" turned out to be table lookups; estimate has real CHAINED computation —
per-service formulas (multiply/add/multiply), cross-service summation (the
Property-16 invariant), tier scaling, and ×12 annualization. The DSL thesis
("deterministic leaves reproduce from prose+JSON, interpreted by a cold LLM") was
verified for lookups+clamps in design; this probe tests it for chained float
arithmetic BEFORE authoring estimate, so any failure surfaces before
generate/feedback are built on top.

## The probe

`.agents/scratchpad/estimate-math-probe/`: a 5-service `design.json` (Fargate
web+worker, ALB, RDS, ElastiCache) + new_vpc (→ post-loop NAT), and a
`rates.json` subset of `pricing-cache.md` with the per-service formulas. A cold
LLM (zero context) computed each line, the total, optimized (×0.70), and annual
(×12), showing all arithmetic, then self-checked by re-adding independently.

Hand-computed expected: Fargate web $36.04, worker $9.01, ALB $22.27, RDS
$108.89, ElastiCache $23.36, NAT $32.85 → **balanced $232.42**; optimized
$162.69; annual $2,789.04 / $1,952.28.

## Result: PASS — chained arithmetic is deterministic

The cold LLM reproduced EVERY figure to the cent, matching the hand-computation:

- Fargate `(cpu/1024×r1 + mem/1024×r2)×730×count` — both tasks exact
  (36.0401→$36.04, 9.010025→$9.01); the nested multiply/add/multiply held.
- ALB fixed+LCU, RDS rate×730+storage×r, ElastiCache rate×730×2 (multi-AZ
  multiplier) — all exact.
- Post-loop NAT add (derived from `vpc_design.mode == new_vpc`, NOT a
  services[] entry) — correctly added.
- Total $232.42 (Property-16); the independent re-grouping self-check matched.
- Optimized ×0.70 and ×12 annualization correct.

So estimate's chained float arithmetic reproduces deterministically from
prose+JSON — the thesis holds for the math-heavy phase, no runtime engine needed.

## The real finding: multi-AZ convention is INCONSISTENT across services

The cold LLM flagged the one genuine ambiguity (exactly what the probe is for):
**RDS had `multi_az: true` in the config, but the RDS formula has no multi-AZ
multiplier** — so it applied the rate as-is (single value). Tracing it to the
actual `pricing-cache.md`:

- **RDS PostgreSQL** rates are labeled **"(On-Demand, Multi-AZ)"** — multi-AZ is
  ALREADY BAKED INTO the rate (db.t4g.medium = 0.129 is the multi-AZ price).
- **ElastiCache Redis** rates are **"Single-AZ pricing. For Multi-AZ,
  approximately double"** — multi-AZ is a **×2 MULTIPLIER applied on top**.
- **Aurora** "replicates across 3 AZs by default" — multi-AZ is **intrinsic**, no
  adjustment.
- **RDS MySQL** is single-AZ "For Multi-AZ, approximately double" — multiplier
  (but MySQL isn't in heroku→aws scope).

So the SAME `multi_az: true` design flag means three different things depending
on service. A naive single formula gets RDS wrong by ~2x (the LLM showed it:
single-AZ-applied $108.89 vs if-doubled $326.59). This is a **correctness
hazard**, not an arithmetic one — and it must be encoded EXPLICITLY in the
estimate knowledge JSON, per service:

- `rds_postgresql`: rate is multi-AZ inclusive → NEVER apply a multi-AZ
  multiplier (multi_az flag is informational only for RDS).
- `elasticache`: rate is single-AZ → apply ×2 when `multi_az == true`.
- `aurora`: rate is 3-AZ intrinsic → no multiplier; multi_az flag informational.

## What this means for authoring

1. **Author estimate as prose + a rates JSON.** The chained math is safe for a
   cold LLM. No engine.
2. **Encode the multi-AZ convention per service in the knowledge JSON** as data
   (e.g. each service's rate carries `multi_az_handling: "baked_in" |
   "multiplier_x2" | "intrinsic"`), so the formula reads the convention rather
   than the author hoping the LLM guesses. This is the knowledge-separation rule
   doing real work: the convention is data, not prose.
3. **EKS pod cost = $0 + post-loop cluster cost** (from the MCP-refactor port
   note) is the analogue of the NAT post-loop add — same shape, gated on the
   (not-yet-authored) EKS design branch. Estimate should be authored EKS-aware
   (handle an `eks_cluster` entry) even though design doesn't emit one yet, so it
   doesn't need retrofitting later.
4. **Pricing-source freshness** (cached vs live MCP, staleness) is a real
   estimate concern but ORTHOGONAL to the math. The DSL has no MCP/network at
   tool time → default to the cached rates JSON with a documented staleness note
   (faithful-port adaptation, same as design's k8s-version constant).

## Net

Estimate's chained cost arithmetic is deterministic from prose + a rates JSON —
PASS, thesis holds. The probe earned its keep by catching the multi-AZ
convention inconsistency (RDS baked-in vs ElastiCache ×2 multiplier vs Aurora
intrinsic) — a ~2x correctness hazard that must be encoded as per-service data in
the rates knowledge, not left to formula prose. Proceed to author estimate under
the two rules (rates + tunables as `knowledge/estimate/`, output shape in a new
`schemas/estimation-infra.schema.json`), EKS-aware, with the multi-AZ convention
explicit per service.
