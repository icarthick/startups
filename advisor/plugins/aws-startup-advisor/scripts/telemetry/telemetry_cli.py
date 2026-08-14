#!/usr/bin/env python3
"""
Telemetry CLI (Phase-1 WALKING SKELETON, Option 2: skill-invoked script).

Same behavior as the MCP server variant, but invoked as a plain CLI the skill runs via
its shell/exec tool — so path resolution happens in SKILL prose (cross-host), not in the
host's MCP config parser (Claude-Code-only). No MCP, no dependencies (stdlib only).

Invoked as `python3 telemetry_cli.py <subcommand>` — stdlib-only, so plain python3 is
preferred over `uv run --script` (no ~/.cache/uv write, more sandbox-robust). Still runs
fine under `uv run --script` if that is the only interpreter available.

Subcommands:
  consent get|grant|revoke
  record --run-id R --phase P --event-name E [--status S] [--attributes '<json>']
  status

Local sink: ~/.migration-to-aws/{telemetry.json, events.jsonl}. Anonymous installId.
record no-ops without consent; fail-open; prints a terse one-line result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.path.expanduser("~")) / ".migration-to-aws"
CONFIG_PATH = STATE_DIR / "telemetry.json"
EVENTS_PATH = STATE_DIR / "events.jsonl"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_config() -> dict[str, Any]:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_config(cfg: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def _ensure_install_id(cfg: dict[str, Any]) -> str:
    install_id = cfg.get("installId")
    if not install_id:
        install_id = str(uuid.uuid4())
        cfg["installId"] = install_id
        cfg.setdefault("consent", None)
        cfg["updatedAt"] = _now_iso()
        _save_config(cfg)
    return install_id


def cmd_consent(action: str) -> str:
    cfg = _load_config()
    _ensure_install_id(cfg)
    act = (action or "").strip().lower()
    if act == "get":
        return f"consent={cfg.get('consent') or 'unset'}"
    if act in ("grant", "revoke"):
        cfg["consent"] = "granted" if act == "grant" else "denied"
        cfg["updatedAt"] = _now_iso()
        _save_config(cfg)
        return f"consent={cfg['consent']}"
    return "error=unknown_action (use get|grant|revoke)"


def cmd_record(
    run_id: str,
    phase: str,
    event_name: str,
    status: str | None,
    attributes_json: str | None,
) -> str:
    try:
        cfg = _load_config()
        install_id = _ensure_install_id(cfg)
        if cfg.get("consent") != "granted":
            return "skipped=no_consent"
        event = {
            "runId": run_id,
            "installId": install_id,
            "timestamp": int(time.time() * 1000),
            "source": os.environ.get("TELEMETRY_SOURCE", "claude-code"),
            "phase": phase,
            "eventName": event_name,
        }
        if status:
            event["status"] = status
        if attributes_json:
            try:
                attrs = json.loads(attributes_json)
                if isinstance(attrs, dict) and attrs:
                    event["attributes"] = attrs
            except Exception:
                pass  # malformed attributes must never break emission
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a") as f:
            f.write(json.dumps(event) + "\n")
        return "recorded"
    except Exception as e:  # fail-open
        return f"soft_error={type(e).__name__}"


def cmd_status() -> str:
    cfg = _load_config()
    count = 0
    try:
        if EVENTS_PATH.exists():
            count = sum(1 for _ in EVENTS_PATH.open())
    except Exception:
        pass
    return (
        f"consent={cfg.get('consent') or 'unset'} "
        f"installId={cfg.get('installId', 'unset')} events={count} sink={EVENTS_PATH}"
    )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="telemetry")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("consent")
    pc.add_argument("action", choices=["get", "grant", "revoke"])

    pr = sub.add_parser("record")
    pr.add_argument("--run-id", required=True)
    pr.add_argument("--phase", required=True)
    pr.add_argument("--event-name", required=True)
    pr.add_argument("--status", default=None)
    pr.add_argument("--attributes", default=None, help="JSON object string")

    sub.add_parser("status")

    args = p.parse_args(argv)
    if args.cmd == "consent":
        print(cmd_consent(args.action))
    elif args.cmd == "record":
        print(cmd_record(args.run_id, args.phase, args.event_name, args.status, args.attributes))
    elif args.cmd == "status":
        print(cmd_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
