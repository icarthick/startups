#!/usr/bin/env bash
# scripts/type-graph/build.sh
#
# Regenerate the DSL type-graph artifacts from source. Run from anywhere.
#   1. extract.ts  reads types/*.ts          -> structural.json   (DERIVED, never hand-edit)
#   2. render.ts   merges + drift-guards      -> type-graph.mmd    (Mermaid, type-level)
#   3. extract-keys.ts reads INTERPRETER+types -> keys.json        (DERIVED, key-level)
#   4. render-keys.ts                          -> key-graph.mmd     (Mermaid, key-level)
#
# The drift guard in render.ts FAILS (exit 1) if semantic-edges.json references a
# type that no longer exists — so a stale committed graph is caught in CI if this
# is wired into `mise run build` (admin-owned mise.toml; flag for review).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
types="$here/../dsl-validator/types"
interp="$here/../../INTERPRETER.md"

node "$here/extract.ts"      "$types"                         > "$here/structural.json"
node "$here/render.ts"       "$here/structural.json" "$here/semantic-edges.json" > "$here/type-graph.mmd"
node "$here/extract-keys.ts" "$types" "$interp"               > "$here/keys.json"
node "$here/render-keys.ts"  "$here/keys.json"                > "$here/key-graph.mmd"

echo "type-graph: regenerated structural.json, type-graph.mmd, keys.json, key-graph.mmd"
