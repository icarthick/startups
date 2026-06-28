# Estimate Phase (DSL port) — VERDICT

**Change:** Ported Phase 4 (Estimate) from the upstream markdown
(`skills/heroku-to-aws/references/phases/estimate/estimate.md` +
`shared/pricing-cache.md`) into the DSL. Estimate is the genuinely MATH-HEAVY
phase — chained per-service cost formulas, the Property-16 sum invariant, tier
scaling, annualization, comparison/ROI, complexity classification, optimization
opportunities, recommendation.

Files authored (full scope, EKS-aware, cache+optional-MCP per the user's call):

- `phases/estimate.phase.md` — thin phase (requires design, re-entry guard on
  generate, 1 cost-engine fragment + validator assembler, advances to generate).
- `phases/estimate/estimate-cost-engine.md` — the data-driven cost engine:
  pricing-source select \u2192 per-service costs (each applying its multi-AZ
  convention) \u2192 post-loop NAT/Route53/EKS \u2192 observability \u2192 totals + tiers \u2192
  Heroku comparison/ROI \u2192 complexity \u2192 optimization \u2192 recommendation. Creates
  `estimation-infra.json`.
- `phases/estimate/estimate-assemble.md` — validator assembler owning the
  Property-16 total invariant, every-service-priced, recommendation/complexity
  gates.
- `knowledge/estimate/aws-pricing.json` — rates + per-service formulas + the
  per-service MULTI-AZ CONVENTION (the probe's key finding).
- `knowledge/estimate/estimate-defaults.json` — tiers, observability heuristics,
  complexity thresholds, optimization catalog, recommendation logic,
  pricing-source/staleness policy.
- `schemas/estimation-infra.schema.json` — the output contract.

## Pre-authoring probe

`test-output/estimate-arithmetic-probe.md` first isolated the chained cost
arithmetic in a small fixture: PASS (deterministic to the cent), and it caught the **multi-AZ convention
hazard** — RDS rate is multi-AZ baked-in, ElastiCache is single-AZ \u00d72, Aurora is
3-AZ intrinsic. A single naive formula would be ~2\u00d7 wrong on one of them. Encoded
as per-service `multi_az_handling` data so the formula reads the convention.

## Cold-LLM end-to-end test: PASS

Against the acme-store design (Fargate web+worker, ALB, Aurora multi-az,
ElastiCache multi-az, CloudWatch-Logs/papertrail, new_vpc, route53) + a $200/mo
billing baseline, a cold LLM executed estimate end-to-end:

- **Chained arithmetic exact**, Property-16 reconciled to **$199.49** via an
  independent re-add. Tiers (\u00d71.5 / \u00d70.7), annualization, Heroku comparison
  (per-tier monthly/annual diff + percent) all correct.
- **Multi-AZ trap avoided cleanly:** Aurora `intrinsic` \u2192 NOT doubled ($59.69,
  not $113.38); ElastiCache `multiplier_x2` \u2192 doubled ($11.68\u2192$23.36). This is
  the result that most mattered \u2014 the per-service convention data made it
  unambiguous.
- Complexity correctly classified **large** (HIPAA \u2192 compliance != none fires
  Large). Optimization opportunities gated right (compute SP + database SP +
  Fargate Spot fire; S3-IA does not \u2014 no S3). Recommendation coherent
  (migrate_optimized, optimized ~30% under Heroku).
- Schema valid, all gates pass \u2192 `HANDOFF_OK`. No closed-vocab violation, no
  unclassifiable file region, no missing rate.

## Findings (fixed)

1. **`unpriced` vs `subsumed` for a CloudWatch-Logs design service (real
   ambiguity, FIXED).** The prose said observability "REPLACES any per-service
   CloudWatch-Logs line," but the engine never emits such a line, and the
   every-service-priced gate didn't say whether the papertrail service is
   "priced" or "unpriced" \u2014 two readings diverged on warnings. Fixed: a
   `CloudWatch Logs` design service is SUBSUMED into the single observability
   block and counts as PRICED (recorded in the observability `note`); never
   marked `unpriced`.
2. **Observability `log_gb` task-vs-service ambiguity (real, FIXED).** The key
   was `fargate_task: 3` but the sum was "over designed services," and a Fargate
   service has `desired_count` tasks \u2014 2 services\u00d73 vs 3 tasks\u00d73 diverge.
   Fixed: renamed the keys to `log_volume_gb_per_service` (`fargate_service`,
   etc.) and stated "per designed service, not per running task."
3. **Annualization round-order (cosmetic, FIXED).** monthly\u00d712 vs
   round(monthly)\u00d712 drifted by cents. Pinned round-then-multiply in both the
   defaults JSON and the totals step.

## EKS-awareness (authored, untested-by-this-fixture)

The cost engine handles an `eks_cluster` design entry (control plane + nodes,
PODS $0 to avoid double-counting) as a post-loop add, even though design's EKS
branch is a stub \u2014 so estimate needs no retrofit when EKS lands. Not exercised by
the Fargate fixture; will be covered by the EKS cross-phase cold-test.

## Pricing source (faithful adaptation)

Cached `aws-pricing.json` is the default + the deterministic cold-test path
(`status: "cached"`). The prose documents that IF an awspricing MCP is available
the LLM may refresh stale/missing rates (live / cached_fallback / unavailable per
service), preserving upstream's hierarchy semantics without requiring network at
tool time. Cache staleness (>30d) \u2192 `cached_stale` + note; infra rates stay
reliable. The fixture ran fully cached (14 days old < 30).

## Net

Estimate is ported and cold-validated end-to-end. **The DSL thesis holds for the
hardest arithmetic phase:** chained float cost math + Property-16 summation
reproduce deterministically from prose + a rates JSON, with no runtime engine \u2014
AND the multi-AZ convention hazard (the one ~2\u00d7 correctness trap) is neutralized
by encoding it as per-service data. Three determinism nits fixed. Next: generate
(multi-fragment + multi-artifact: terraform/ + guide + scripts) \u2014 the assembler's
multi-artifact stress test; and the EKS cross-phase pass (design branch + the
already-authored estimate handling).
