# Cursor hook registration (experimental)

Registers the same `emit.mjs` from Cursor instead of Claude Code. Two ways to do it,
and they are not equivalent.

## Option A — as a Cursor plugin (preferred, zero footprint)

`.cursor-plugin/plugin.json` in the plugin root makes this directory a Cursor
plugin. Cursor then discovers `skills/` on its own, and the manifest points `hooks`
at `hooks/telemetry/cursor/hooks.json` — deliberately *not* the sibling
`hooks/hooks.json`, which holds Claude Code's PascalCase event names and
`${CLAUDE_PLUGIN_ROOT}` argument arrays. Naming an explicit path replaces folder
discovery for that component, so the two never collide.

This is the shape a shipped Cursor integration would take: hooks arrive with the
plugin, so nothing is written into the customer's repository or global config.

For local testing, Cursor loads plugins from `~/.cursor/plugins/local/`:

```bash
mkdir -p ~/.cursor/plugins/local
ln -s ~/dev/github/startups/advisor/plugins/aws-startup-advisor \
      ~/.cursor/plugins/local/aws-startup-advisor
```

Reload the window, then check **Customize → Plugins**. Expect 9 skills and 3 hooks.
Local plugin imports are gated by the **Allow Local Plugin Imports** admin setting,
which is off by default on Enterprise.

Hook commands here are **plugin-root-relative** (`./hooks/telemetry/emit.mjs`),
following the convention in Cursor's own plugin examples. Resolution for plugin
hook commands is not spelled out in the docs, so if nothing fires, this is the
first thing to suspect — substitute absolute paths to confirm.

## Option B — a project `.cursor/hooks.json` (test only)

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

## Which option to use

**Option B writes into the customer's project**, the one registration site the
design explicitly rejects: it enters their version control and their teammates'
sessions. Fine for a local test, wrong to ship. Use it only to isolate a problem
with Option A.

**Option A is the shippable shape**, but it is not how Cursor users install this
today. `setup.md` sends every non-Claude agent through
`npx skills add … --skill '*'`, which installs **skills only** — no manifest, no
hooks — and our Claude Code registration lives in skill frontmatter, which Cursor
does not read. So a Cursor user today gets the migration skills with **no telemetry
at all**, silently. Closing that means publishing this as a Cursor plugin through
the marketplace or a private team marketplace, not just adding a manifest.

## Still unresolved

- **No plugin data directory** is documented for the Cursor format, so `installId`
  falls back to `~/.aws-startups-plugins`. Workable, arguably better since it
  survives plugin updates, but a fallback rather than a designed location.
- **Cloud agents support neither `sessionStart` nor `sessionEnd`**, so there is no
  final sweep there at all.
- **Endpoint configuration.** A GUI-launched Cursor does not inherit a shell's
  environment, so `AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT` is unset and the emitter
  advances the snapshot while sending nothing — and that loss is permanent. Launch
  Cursor from a terminal that has the variable, or use a `sessionStart` hook
  returning `env`, which Cursor propagates to every later hook in the session. Only
  the latter works for a plugin shipped to someone else.
