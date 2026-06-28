# Design Phase (DSL port) — VERDICT

**Change:** Ported Phase 3 (Design) from the upstream pure-markdown skill
(`skills/heroku-to-aws/references/phases/design/design.md` + the six
`design-refs/*-table.md`) into the DSL. Design is the **first MATH-bearing
phase** and the DSL thesis's load-bearing test ("does prose + a JSON lookup
table make a cold LLM compute the SAME numbers?").

Files authored:

- `phases/design.phase.md` — thin phase: re-entry guard, preconditions on
  inventory + preferences, `_knowledge` guards (load a table only when its
  resource type is present), ONE mapping fragment + one validator assembler,
  plus a trigger-gated EKS fragment (stub).
- `phases/design/design-mapping.md` — the single fragment: deterministic
  single-pass mapping (formation→Fargate, postgres→RDS/Aurora, redis→
  ElastiCache, kafka→MSK, other addons→fast-path, pipeline→warn, space→VPC),
  then VPC + security-group design and Fir notation. CREATES `aws-design.json`.
- `phases/design/design-assemble.md` — no-op/validator assembler owning the
  schema contract + the ROUTE OUTPUT GATES (re-reads the inventory to know what
  the design was obligated to produce).
- `phases/design/design-eks.md` — EKS branch STUB that halts loudly (default-
  safe: only reached on an opt-in `eks-*` preference; not yet authored).
- `knowledge/design/{dyno-fargate,postgres-rds,redis-elasticache,kafka-msk,
  fast-path-addons}.json` — the five lookup tables as DATA, each carrying the
  "provenance only — do not recompute" guard the arithmetic probe prescribed.
- `schemas/aws-design.schema.json` — artifact contract (per-entry required
  fields, vpc conditional, no-clustering `not`).

## Pre-authoring probe

`test-output/design-arithmetic-probe.md` first isolated the numeric work and
established: design's "arithmetic" is table LOOKUP + a 0–100 clamp + tier
branches, and the real determinism threat is the RE-DERIVE temptation (the table
prose describes its own derivation, e.g. `performance-l` Heroku 14336 MB →
Fargate 16384 MiB). The fix carried into the knowledge JSONs: demote source
figures to clearly-labeled provenance + an explicit "do not recompute" note.

## Cold-LLM tests: 2 fixtures, both PASS

**Fixture 1 (acme-store, easy):** Fargate + RDS/Aurora + ElastiCache + fast-path,
plus pipeline-warning, new_vpc, and unknown-dyno reject. Cold LLM produced the
expected `aws-design.json`, all route gates passed, `HANDOFF_OK`. But the cold
LLM correctly flagged the fixture as TOO EASY to validate the headline math
claims (no clamp triggered, no re-derive trap row present, standard-0's RDS and
Aurora columns are identical so the engine branch was indistinguishable).

**Fixture 2 (bigapp, hard — built in response to that critique):** every trap
fired and was handled correctly:

- `performance-l` web qty 150 → `task_memory` **16384** (lookup, NOT the 14336
  re-derive trap) AND `desired_count` **clamped 150→100** + warning.
- `Performance-L` worker → case-insensitive match, also 16384.
- `standard-3` postgres, `database_ha: multi-az` → **RDS** PostgreSQL,
  `db.m6g.xlarge` (the RDS column — distinct from Aurora `db.r6g.xlarge`, so the
  engine branch is now PROVEN), `multi_az: true`, storage 512, rds_proxy
  resolved to `true` from `config.connection_pooling` (NOT the colliding
  `src_connection_pooling` provenance column — an adversarial value collision
  the prose forced through correctly).
- `standard-1` kafka → `kafka.m5.xlarge`, **3 brokers / 3 AZs** (standard tier),
  topology 100/400/rf3.
- `bonsai` → normalized via prefix-alias to `bonsai elasticsearch` → Amazon
  OpenSearch.
- `weirdaddon` → **deferred**.
- space WITH peering → **existing_vpc** + subnet_ids; restricted SG with exactly
  443/5432/9092 (6379 correctly omitted — no Redis designed).
- Fir app → detect-only deferral note, NO ARM/Graviton/CNB anywhere.

Both runs reached `HANDOFF_OK`; `metadata.total_services` matched
`services[].length` (incl. the ALB-counts-as-a-service rule).

## Findings (fixed)

1. **Closed-vocabulary violations (real, FIXED).** Fixture-1's cold LLM caught
   three undefined `_`-keys a strict interpreter would HALT on:
   `_status: NOT_YET_AUTHORED` (inert annotation in frontmatter),
   `_halt: true` (EKS stub meta), and the `_eks-compute-mode` pseudo-artifact
   sigil. Fixed: dropped `_status` (moved to a non-`_` comment), removed `_halt`
   (the stub step halts via the defined `_halt_and_inform` action in prose), and
   re-expressed the EKS gate as the phase's `_trigger._when` plain-language
   condition over the preference. Also ADDED `_when` as a documented fragment
   `_trigger` form in INTERPRETER (a real gap — a fragment can be gated on an
   input VALUE, not just a file/artifact). Fixture-2 confirmed: NO closed-vocab
   violation remains.
2. **Empty `_cases: {}` decorative (FIXED).** The `map_resources` meta listed
   `_cases` with empty bodies while the real branch logic was the FORM-2b prose.
   Removed `_cases`; kept `_branch_on` and a note that the prose IS the case
   bodies.
3. **`total_services` ALB-count ambiguity (FIXED).** Made explicit that a web
   formation contributes TWO services (Fargate + ALB) and `total_services` is
   the true `services[]` length.
4. **`rds_proxy` provenance footgun (FIXED).** The postgres table exposed a
   `connection_pooling` column with the SAME name as the inventory field the
   `_rds_proxy` rule reads — inviting a wrong-source read. Renamed the column to
   `src_connection_pooling` and documented it as provenance-not-the-source.
   Fixture-2 (where both are `true`) confirmed the prose forces the correct
   field.
5. **Fast-path non-determinism for non-CloudWatch services (FIXED).** Fixture-2
   showed the prose only prescribed `aws_config` for CloudWatch Logs, so the
   OpenSearch `service_id`/`aws_config` shape was invented (two LLMs could
   differ). Fixed: prescribed a deterministic `service_id`
   (`{primary_aws_service_snake_case}:{app}:{addon}`) and a minimal default
   `aws_config` per mapping type.
6. **Security-group `name` non-determinism (FIXED).** SG names were uncoined.
   Prescribed deterministic names (`{primary_app}-restricted-sg` /
   `{primary_app}-app-sg`).

## EKS scope (flagged, not a defect)

The EKS compute branch (opt-in via clarify's `eks-managed`/`eks-or-ecs`) is NOT
yet authored in the DSL — `design-eks.md` is a loud-halt stub, gated so the
default Fargate path is complete and an EKS preference fails visibly rather than
silently falling back. Authoring it is the all-or-nothing port of upstream
`design-eks.md` + `eks-mapping-table.md` (mirror the MCP refactor's EKS port:
one `eks_cluster` aggregate sized post-loop from all formations,
`knowledge/design/eks-pod-sizing.json`). Tracked follow-up.

## Net

Design is ported and cold-validated on BOTH an easy and a deliberately hard
fixture. **The DSL thesis holds for the math-bearing phase:** prose + a JSON
lookup table (with the provenance/do-not-recompute guard) reproduced every
numeric leaf deterministically — the clamp, the re-derive trap (on two
formations), the case-fold, the engine-column branch, the tier branch, the
proxy-from-the-right-field — with no runtime engine. Six findings fixed (three
of them genuine closed-vocab violations that a CI validator must also catch).
Flag forward: ESTIMATE is the genuinely harder arithmetic (chained
multiply/sum/round, premium/optimized tier derivation, post-loop cluster costs)
— design passing does NOT pre-clear it; probe estimate the same way before
building generate on top.

## Addendum (2026-06-28) — knowledge/contract/procedure separation

Applied the **knowledge-separation rule** (now in
`docs/unit-taxonomy-spec.md`): a `.md` is PROCEDURE; data that evolves
independently of the algorithm must be a separate referenced artifact. Test:
"would someone change this value for a reason unrelated to the algorithm?" —
yes → knowledge, no → procedure; the output SHAPE is a third thing (contract →
schema).

Extracted from `design-mapping.md` prose into a new
`knowledge/design/design-defaults.json` tunable-constants sheet: Postgres
`engine_version`, the new_vpc CIDR/subnet topology, SG ports + name patterns +
egress, the container-image / log-group patterns + default retention, the Fir
notation strings, and the fixed warning messages. De-duplicated the 0–100 clamp
(references the dyno table only now). The output JSON skeletons were NOT
extracted — they are CONTRACT, so the prose defers to `aws-design.schema.json`
(names key fields for readability; schema is authoritative). Algorithm /
branches / "do-not-recompute" guards stayed in the `.md`.

**Regression cold-test (hard fixture 2, re-run):** PASS, behavior-preserving.
The cold LLM produced output IDENTICAL in substance to the inlined-constants
run, resolved every referenced constant from `design-defaults.json` with no
dangling references, found no closed-vocab violation, and judged the procedure
STILL readable as an algorithm. Moving constants changed only WHERE values live,
not WHICH values the algorithm produces. Incidentally confirmed the fast-path
`service_id` determinism fix (`amazon-opensearch:bigapp:bonsai`).

Next: retrofit the same separation to discover + clarify (clarify's defaults
table / region lists / validation regexes are knowledge by this test), each with
a behavior-preserving re-test.
