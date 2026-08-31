# Cursor hook registration (experimental)

Registers the same `emit.mjs` from Cursor instead of Claude Code. Exploratory — not
a shipping path. See the "what would have to change to ship" section at the end.

## Install for a test

Cursor reads `hooks.json` from the **project you open**, not from wherever the
plugin lives, so this goes in the repository being migrated:

```bash
REPO=~/tel-demo                                    # the workload you will migrate
PLUGIN=~/dev/github/startups/advisor/plugins/aws-startup-advisor

mkdir -p "$REPO/.cursor"
sed "s|__PLUGIN__|$PLUGIN|g" \
  "$PLUGIN/hooks/telemetry/cursor/hooks.json.template" > "$REPO/.cursor/hooks.json"
```

`~/.cursor/hooks.json` works too and applies to every project, but it persists
after the test and is global — prefer the project file, and delete it when done.

Cursor watches these files and reloads on save. Confirm registration under
**Customize → Hooks**, and watch the Hooks output channel for invocations.

## Why these three events

| Event | Why |
|---|---|
| `afterFileEdit` | Fires for **any** agent edit and hands over `file_path`. Closer to what this design actually wants than a tool matcher, because it does not care which tool wrote the file |
| `stop` | Reconcile at the end of the agent loop, the same role it plays on Claude Code |
| `sessionEnd` | Final sweep. Carries a `reason` (`completed`, `aborted`, `error`, `window_close`, `user_close`) that Claude Code does not provide |

**All three run in `--reconcile` / `--session-end` mode — none parses a path from
the payload.** That is deliberate: Cursor's `postToolUse` `tool_input` shape is
undocumented, and reconcile mode reads state from disk instead, so a payload-field
surprise cannot cost an event. `postToolUse` with a `Write` matcher is available if
incremental delivery is ever wanted, but it buys little here.

## Host differences the emitter absorbs

Handled by fallbacks, so one script serves both hosts with no branching:

| | Claude Code | Cursor |
|---|---|---|
| Session id | `session_id` | `conversation_id` on tool/file/stop hooks; `session_id` only on session hooks |
| Working dir | `cwd` | `cwd` on tool hooks; `workspace_roots[0]` on file hooks |
| Edited path | `tool_input.file_path` | top-level `file_path` on `afterFileEdit` |
| Reported `source` | `CLAUDE_CODE` | `CURSOR`, detected from `CURSOR_VERSION` / `CURSOR_PROJECT_DIR` |
| Args | verbatim array, no shell | part of the command **string**, so shell quoting applies |

`AWS_STARTUP_ADVISOR_TELEMETRY_SOURCE` forces the reported host when testing.

If a hook fires but finds no path, the trace records the payload's **key names**
(never values) — that is how to discover Cursor's real `tool_input` spelling if
`postToolUse` is tried:

```
{"mode":"post_tool_use","outcome":"not_phase_status",
 "detail":"no_path keys=hook_event_name,conversation_id,... tool_input=mystery_key"}
```

## Exit codes

Cursor treats exit `0` as success, exit `2` as **block**, and any other code as a
failed hook that proceeds anyway (`failClosed` defaults to `false`). `emit.mjs`
always exits 0, so it can never block an edit, a shell command or a turn.

## What would have to change to ship this

The template above writes into the customer's project, which is the one
registration site the design explicitly rejects — it enters their version control
and their teammates' sessions. Shipping would instead mean publishing a **Cursor
plugin**: a `.cursor-plugin/plugin.json` manifest with `hooks/hooks.json`
discovered automatically, installed from Customize at project or user scope. That
is the only Cursor registration site with the same zero-footprint property as the
Claude Code plugin.

Today Cursor users install via `npx skills add … --skill '*'`, which installs
**skills only** — no manifest, no hooks — and our Claude Code registration lives in
skill frontmatter, which Cursor does not read. So a Cursor user currently gets the
migration skills with no telemetry at all, silently.

Also unresolved: Cursor documents no plugin data directory, so `installId` would
fall back to `~/.aws-startups-plugins`; and cloud agents support neither
`sessionStart` nor `sessionEnd`, so there is no final sweep there.
