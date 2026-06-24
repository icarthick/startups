#!/usr/bin/env bash
# Launcher for the migration-tools MCP server.
# Resolves the server path relative to this script, not the caller's CWD.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec uvx --from "$SCRIPT_DIR/server" serve "$@"
