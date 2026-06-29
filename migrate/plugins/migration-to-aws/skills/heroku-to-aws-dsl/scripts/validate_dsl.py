#!/usr/bin/env python3
"""
validate_dsl.py — conformance validator for the heroku-to-aws DSL skill.

Enforces the rules specified in INTERPRETER.md + docs/unit-taxonomy-spec.md so
that "the author writes domain logic; structure enforces the meta" is a CHECK,
not a hope. Stdlib only (json + re). Run from the skill root or pass it.

Checks (see docs/unit-taxonomy-spec.md conformance checklist):
  JSON      every knowledge/schema/*.json parses
  REGIONS   unit file = frontmatter -> H1 -> <=1 ## Orientation -> ## Step:* ; nothing else
  SUBSET    every file in a step _knowledge/_templates is declared in its phase
  GUARDSCOPE every phase _when guard references only the phase _input (heuristic)
  USES      every [_uses: F] in a step body names a file in that step's meta _knowledge/_templates;
            every bare `*.json|*.tmpl|*.sh` knowledge/template ref in a step body is tagged
  NORESTATE no step body restates an interpreter rule (load/gate/advance) — heuristic
  ORPHAN    every knowledge/ + templates/ file is referenced by some unit; every reference resolves
  XTABLE    cross-table key coverage: every value a producer table emits is a key
            in the consumer table (e.g. design rds_instance_class -> estimate rates)

Exit non-zero if any hard violation. Heuristic checks print warnings (do not fail
the build) unless --strict.
"""
import json, re, sys, os, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "."
STRICT = "--strict" in sys.argv
errors, warns = [], []
def err(m): errors.append(m)
def warn(m): warns.append(m)

def rel(p): return os.path.relpath(p, ROOT)

def _load_json(p):
    """Parse JSON; return None on failure (the JSON-validity check reports the error)."""
    try:
        return json.load(open(p))
    except (ValueError, OSError):
        return None

# ---------- frontmatter + body split ----------
def split_unit(text):
    """Return (frontmatter_str, body_str). Frontmatter is the first --- ... --- block."""
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.S)
    if m: return m.group(1), m.group(2)
    return "", text

def fm_files(fm):
    """All knowledge/templates/schemas file: paths declared in a frontmatter block."""
    return set(re.findall(r'file:\s*(knowledge/[^\s,}]+|templates/[^\s,}]+|schemas/[^\s,}]+)', fm))

def fm_when_guards(fm):
    """[(file, when_text)] for guarded knowledge/templates entries."""
    out = []
    for m in re.finditer(r'\{\s*file:\s*([^\s,}]+)\s*,\s*_when:\s*"([^"]*)"', fm):
        out.append((m.group(1), m.group(2)))
    return out

def fm_input(fm):
    """The _input artifact basenames (for guard-scope)."""
    blk = re.search(r'_input:\s*\n((?:\s*-\s*.*\n)+)', fm)
    files = set()
    if blk:
        for ln in blk.group(1).splitlines():
            mm = re.search(r'-\s*([^\s{].*\S)', ln)
            if mm and "file:" not in ln:
                files.add(mm.group(1).strip().strip('"'))
    return files

# ---------- step extraction (FORM 2b body) ----------
def steps(body):
    """Return [(step_id, meta_str, prose_str)] for each ## Step: section."""
    out = []
    parts = re.split(r'\n## Step:\s*(\S+)\s*\n', "\n" + body)
    # parts: [pre, id1, body1, id2, body2, ...]
    for i in range(1, len(parts), 2):
        sid = parts[i]
        sbody = parts[i+1] if i+1 < len(parts) else ""
        mm = re.search(r'```meta\n(.*?)\n```', sbody, re.S)
        meta = mm.group(1) if mm else ""
        prose = sbody[mm.end():] if mm else sbody
        out.append((sid, meta, prose))
    return out

def meta_knowledge(meta):
    out = set()
    for m in re.finditer(r'_(?:knowledge|templates):\s*\[([^\]]*)\]', meta):
        out |= set(re.findall(r'(knowledge/[^\s,\]]+|templates/[^\s,\]]+|schemas/[^\s,\]]+)', m.group(1)))
    return out

def top_sections(body):
    return re.findall(r'^##\s+(.*)$', body, re.M)

# ---------- load all units ----------
phase_files = sorted(glob.glob(f"{ROOT}/phases/*.phase.md"))
unit_files = sorted(glob.glob(f"{ROOT}/phases/*/*.md"))

phase_decl = {}   # phase name -> set(declared knowledge/template files)
for pf in phase_files:
    name = os.path.basename(pf)[:-len(".phase.md")]
    fm, _ = split_unit(open(pf).read())
    phase_decl[name] = fm_files(fm)
    # GUARDSCOPE: guards reference only _input
    inp = fm_input(fm)
    for f, when in fm_when_guards(fm):
        # tokens in the guard that look like artifact refs
        refs = re.findall(r'([a-z0-9_]+\.json)', when)
        for r in refs:
            if r not in inp and r not in {os.path.basename(x) for x in inp}:
                warn(f"GUARDSCOPE {rel(pf)}: guard for {f} names '{r}' not in _input {sorted(inp)}")

# ---------- JSON validity ----------
for jf in glob.glob(f"{ROOT}/knowledge/**/*.json", recursive=True) + glob.glob(f"{ROOT}/schemas/*.json"):
    try: json.load(open(jf))
    except Exception as e: err(f"JSON {rel(jf)}: {e}")

# ---------- per-unit checks ----------
INTERP_RULE_RE = re.compile(
    r'\b(load only|do not load|never load|sole load decision|uses annotation|'
    r'advance only after|never advance|already loaded|already in context)\b', re.I)
REF_RE = re.compile(r'`([a-z0-9_./-]+\.(?:json|tmpl|sh))[^`]*`')  # backtick file ref in prose
USES_RE = re.compile(r'\[_uses:\s*([^\]]+)\]')

referenced_files = set()  # for ORPHAN

for uf in unit_files:
    text = open(uf).read()
    fm, body = split_unit(text)
    of = re.search(r'_of_phase:\s*(\w+)', fm)
    phase = of.group(1) if of else None
    decl = phase_decl.get(phase, set())
    referenced_files |= fm_files(fm)

    # REGIONS: top-level ## sections must be Orientation (<=1) then Step: only
    secs = top_sections(body)
    nonstep = [s for s in secs if not s.startswith("Step:")]
    orient = [s for s in nonstep if s.strip() == "Orientation"]
    bad = [s for s in nonstep if s.strip() != "Orientation"]
    if len(orient) > 1: err(f"REGIONS {rel(uf)}: more than one ## Orientation")
    if bad: err(f"REGIONS {rel(uf)}: forbidden trailing/extra section(s): {bad}")

    for sid, meta, prose in steps(body):
        used = meta_knowledge(meta)
        referenced_files |= used
        # SUBSET: every step-listed file declared by the phase
        for f in used:
            if phase and f not in decl:
                err(f"SUBSET {rel(uf)} step '{sid}': _knowledge '{f}' not in phase {phase} _knowledge")
        prose_nocode = re.sub(r'```.*?```', '', prose, flags=re.S)
        # USES marker: tagged refs must be in this step's meta set
        tagged = set()
        for tag in USES_RE.findall(prose_nocode):
            tagf = tag.strip()
            tagged.add(tagf)
            if not any(os.path.basename(d) == tagf or d == tagf or d.endswith("/"+tagf) for d in used):
                err(f"USES {rel(uf)} step '{sid}': [_uses: {tagf}] not in step meta _knowledge/_templates {sorted(used)}")
        # USES: each structure-owned file the step's prose REFERENCES must be tagged
        # at least once in that step (tag once per (step,file), not per occurrence).
        referenced_in_prose = set()
        for m in REF_RE.finditer(prose_nocode):
            base = os.path.basename(m.group(1))
            owned = next((d for d in (used | decl)
                          if os.path.basename(d) == base
                          or os.path.basename(d).split('.')[0] == base.split('.')[0]), None)
            if owned:
                referenced_in_prose.add(base)
        for base in referenced_in_prose:
            if not any(t == base or os.path.basename(t) == base for t in tagged):
                warn(f"USES {rel(uf)} step '{sid}': structure-owned ref `{base}` is never tagged "
                     f"(add [_uses: {base}] at its first mention)")

        # NORESTATE: step body must not restate an interpreter rule
        if INTERP_RULE_RE.search(prose_nocode):
            warn(f"NORESTATE {rel(uf)} step '{sid}': step prose may restate an interpreter rule "
                 f"(matched '{INTERP_RULE_RE.search(prose_nocode).group(0)}')")

# ---------- XTABLE: cross-table key coverage (producer emits -> consumer keys) ----------
# Every value the producer's rows emit in <field> MUST be a key in the consumer
# table at <path>. Catches the RDS-style gap (design emits db.m6g.* but estimate's
# rate table only had db.t4g.* -> silent unpriced).
XTABLE_LINKS = [
    ("knowledge/design/postgres-rds-sizing.json", "rds_instance_class",
     "knowledge/estimate/aws-pricing.json", "rds_postgresql.instances"),
    ("knowledge/design/postgres-rds-sizing.json", "aurora_instance_class",
     "knowledge/estimate/aws-pricing.json", "aurora_postgresql.instances"),
    ("knowledge/design/redis-elasticache-sizing.json", "node_type",
     "knowledge/estimate/aws-pricing.json", "elasticache.nodes"),
    ("knowledge/design/kafka-msk-sizing.json", "broker_instance_type",
     "knowledge/estimate/aws-pricing.json", "msk.brokers"),
    ("knowledge/design/eks-pod-sizing.json", "node_type",
     "knowledge/estimate/aws-pricing.json", "eks.node_rates_monthly"),
]
def _dig(d, path):
    for k in path.split('.'):
        d = d.get(k, {}) if isinstance(d, dict) else {}
    return d
for prod, field, cons, path in XTABLE_LINKS:
    pp, cp = f"{ROOT}/{prod}", f"{ROOT}/{cons}"
    if not (os.path.isfile(pp) and os.path.isfile(cp)):
        continue
    pdata = _load_json(pp)
    cdata = _load_json(cp)
    if pdata is None or cdata is None:
        continue  # malformed JSON already reported by the JSON check
    rows = pdata.get("rows", {})
    emitted = {r[field] for r in rows.values() if isinstance(r, dict) and field in r}
    cmap = _dig(cdata, path)
    keys = set(cmap.keys()) if isinstance(cmap, dict) else set()
    missing = emitted - keys
    if missing:
        err(f"XTABLE {prod}.{field} emits {sorted(missing)} not present as keys in "
            f"{cons}.{path} (consumer would look these up as missing)")

# ---------- ORPHAN: every knowledge/template file referenced; every ref resolves ----------
on_disk = set(rel(p) for p in glob.glob(f"{ROOT}/knowledge/**/*.json", recursive=True)
              + glob.glob(f"{ROOT}/templates/**/*", recursive=True) if os.path.isfile(p))
on_disk = {p for p in on_disk if not p.endswith(".DS_Store")}
ref_norm = {r if r.startswith(("knowledge/","templates/","schemas/")) else r for r in referenced_files}
for r in ref_norm:
    if r.startswith(("knowledge/","templates/")) and not os.path.isfile(f"{ROOT}/{r}"):
        err(f"ORPHAN {r}: referenced by a unit but not on disk (dangling reference)")
for d in on_disk:
    if d.startswith(("knowledge/","templates/")) and d not in ref_norm:
        warn(f"ORPHAN {d}: on disk but referenced by no unit (orphan data)")

# ---------- report ----------
print(f"DSL validator: {len(phase_files)} phases, {len(unit_files)} units")
for w in warns: print(f"  WARN  {w}")
for e in errors: print(f"  ERROR {e}")
hard = len(errors) + (len(warns) if STRICT else 0)
if hard:
    print(f"FAIL: {len(errors)} error(s)" + (f", {len(warns)} warning(s) (strict)" if STRICT else f"; {len(warns)} warning(s)"))
    sys.exit(1)
print(f"OK ({len(warns)} warning(s))" if warns else "OK")
