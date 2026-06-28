# Design Arithmetic Probe — FINDING (pre-authoring)

**Why this probe:** the HANDOFF flagged design as "the arithmetic checkpoint —
the can-the-LLM-do-math-right-from-prose question, still UNTESTED." Before
authoring design.phase.md, I isolated and cold-tested the actual numeric work to
learn whether the DSL thesis (deterministic leaves expressed as prose + JSON
table, interpreted by a cold LLM) holds for math-bearing phases — so a failure
would surface BEFORE estimate/generate are built on top.

## What the design phase's "arithmetic" actually is

Reading the upstream `design.md` + `dyno-type-table.md` end-to-end, the design
phase is **almost entirely table LOOKUPS, not computation**:

- Dyno → Fargate: exact-match row read (`task_cpu`/`task_memory` are columns).
- Postgres/Redis/Kafka: instance class / node type / broker type are columns.
- The ONLY genuine numeric operations are: (a) `desired_count` clamp to 0–100,
  (b) Kafka broker/AZ count = 2-or-3 (a tier branch, not math), (c) "≥ table
  storage" (a floor, read-from-table).

So the feared "arithmetic" is thin. The REAL risk for a lookup table is
different and subtler: the table's prose describes the table's _derivation_
("smallest Fargate allocation that meets or exceeds the dyno's memory"), which
can TEMPT a cold LLM to RE-DERIVE a value instead of just reading the column —
especially where the source and target numbers differ (e.g. `performance-l`:
Heroku 14336 MB vs Fargate 16384 MiB). That re-derivation, not arithmetic
difficulty, is the determinism threat here.

## The probe

Fixture (`.agents/scratchpad/design-math-probe/`): a dyno-sizing knowledge JSON
authored DSL-style (data, with an explicit "provenance only — do not recompute"
note on the source columns) + 5 deliberately adversarial formations:

1. `standard-2x`, web, qty 3 — baseline + ALB.
2. `Performance-L`, worker, qty 1 — CASE mismatch + the re-derive trap (14336 vs
   16384).
3. `standard-1x`, clock, qty 0 — qty 0 must NOT clamp (0 is in range).
4. `performance-2xl`, worker, qty 250 — must clamp to 100 + warn.
5. `hobby`, worker, qty 2 — unknown type, must reject (no entry) + warn.

A cold LLM (fresh Claude, zero repo context) was told to "apply the rules
EXACTLY, do not be clever, do not re-derive."

## Result: PASS — every case, including all traps

- **Re-derive trap avoided:** `performance-l` → memory **16384** (the column),
  NOT 14336. It read, did not recompute. This is the result that most mattered.
- Case-insensitive match (`Performance-L` → `performance-l`). ✓
- `qty 0` → desired_count 0, NOT clamped. ✓
- `qty 250` → clamped to 100 + clamp warning. ✓
- `hobby` → rejected, no service entry, not-found warning. ✓
- Self-check counts exact: 5 services (4 Fargate + 1 ALB), 2 warnings, 1
  rejected — matches the hand-computed expected set.

## What this means for authoring

1. **Design is safe to author as prose + JSON lookup.** The determinism risk for
   design is the re-derive temptation, and it was neutralized by (a) putting the
   numbers in a DATA table keyed for exact lookup, and (b) an explicit
   "provenance only — do not recompute" guard on the source columns. CARRY BOTH
   into the real knowledge JSON: keep `fargate_cpu`/`fargate_memory` as the
   lookup result, and DEMOTE the heroku source figures to a clearly-labeled
   provenance field (or drop them) so nothing invites re-derivation.
2. **The clamp + reject + case-fold all worked from prose alone** — no need to
   move them into code. The "must this leaf be deterministic?" fork for design
   resolves to: lookups + a 0–100 clamp + tier branches, ALL of which a cold LLM
   executed correctly. Design does NOT need a runtime engine.
3. **The genuine arithmetic checkpoint is ESTIMATE, not design.** Estimate is
   where real computation lives: rate × hours × quantity, cross-service
   summation, premium/optimized tier derivation, cluster-cost post-loop adds.
   Multi-step chained arithmetic with intermediate rounding is a harder
   determinism test than a single lookup+clamp. Re-run a probe like this for
   estimate's cost math (chained multiply/sum/round) BEFORE trusting it — that
   is the real fork the thesis hinges on, and it is still untested. Design
   passing does NOT pre-clear estimate.

## Net

Cold LLM reproduced the design sizing deterministically, including the
re-derivation trap, the zero-vs-clamp boundary, and the unknown-type rejection.
Design can be authored in the DSL as prose + a lookup JSON, with the explicit
"provenance, do not recompute" guard baked into the table. Proceed to author
design. Flag forward: estimate's chained cost arithmetic is the genuinely
untested math fork — probe it the same way before building generate on it.
