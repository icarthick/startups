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
         [--skill S] [--plugin-version V]
  status

Local sink: ~/.migration-to-aws/{telemetry.json, events.jsonl}. Anonymous installId.
Optional network sink: if $MIGRATE_TELEMETRY_ENDPOINT is set, `record` also POSTs the
event to the migrate-api telemetry route (fail-open; the local write happens regardless).
record no-ops without consent; fail-open; prints a terse one-line result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.path.expanduser("~")) / ".migration-to-aws"
CONFIG_PATH = STATE_DIR / "telemetry.json"
EVENTS_PATH = STATE_DIR / "events.jsonl"

# Optional network sink. When set, `record` ALSO POSTs the event to this endpoint
# (in addition to the local file). Absent → local-file only (offline/skeleton mode).
# The endpoint is the migrate-api telemetry route base, e.g.
#   https://<host>/v1/telemetry   (runId is appended: /v1/telemetry/<runId>/event)
ENDPOINT_ENV = "MIGRATE_TELEMETRY_ENDPOINT"
POST_TIMEOUT_S = 3.0

# Map the plugin's internal lowercase/dotted vocabulary to the migrate-api enums
# (TelemetrySource / TelemetryPhase / TelemetryEventName).
_SOURCE_MAP = {
    "claude-code": "CLAUDE_CODE",
    "claude": "CLAUDE_CODE",
    "codex": "CODEX",
    "cursor": "CURSOR",
}
_EVENT_NAME_MAP = {
    "phase.completed": "PHASE_COMPLETED",
    "phase.failed": "PHASE_FAILED",
    "telemetry.consent_set": "TELEMETRY_CONSENT_SET",
}


def _api_source(raw: str) -> str:
    return _SOURCE_MAP.get((raw or "").strip().lower(), "OTHER")


def _api_event_name(raw: str) -> str:
    key = (raw or "").strip().lower()
    return _EVENT_NAME_MAP.get(key, key.upper().replace(".", "_").replace("-", "_"))


def _api_enum(raw: str | None) -> str | None:
    # phase / skill: uppercase, hyphens → underscores (discover→DISCOVER, gcp-to-aws→GCP_TO_AWS)
    if raw is None:
        return None
    return raw.strip().upper().replace("-", "_")


def _stringify_attrs(attrs: dict[str, Any]) -> dict[str, str]:
    # The API's `attributes` is map<string,string>; booleans/numbers → strings.
    out: dict[str, str] = {}
    for k, v in attrs.items():
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        else:
            out[k] = str(v)
    return out


def _post_event(run_id: str, event: dict[str, Any], skill: str | None, plugin_version: str) -> str | None:
    """POST the API-shaped payload. Returns None on success, else a short error tag.
    Fail-open: the caller ignores failures beyond recording them in the return line."""
    base = os.environ.get(ENDPOINT_ENV, "").strip().rstrip("/")
    if not base:
        return None  # no endpoint configured → local-file only
    payload: dict[str, Any] = {
        "runId": run_id,
        "installId": event["installId"],
        "timestamp": event["timestamp"],
        "source": _api_source(event.get("source", "")),
        "pluginVersion": plugin_version,
        "skill": _api_enum(skill) or "GCP_TO_AWS",
        "phase": _api_enum(event.get("phase")),
        "eventName": _api_event_name(event.get("eventName", "")),
    }
    if event.get("status"):
        payload["status"] = event["status"]
    if isinstance(event.get("attributes"), dict) and event["attributes"]:
        payload["attributes"] = _stringify_attrs(event["attributes"])
    url = f"{base}/{run_id}/event"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT_S) as resp:
            code = resp.getcode()
            return None if 200 <= code < 300 else f"http_{code}"
    except urllib.error.HTTPError as e:
        return f"http_{e.code}"
    except Exception as e:
        return type(e).__name__


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
    skill: str | None = None,
    plugin_version: str = "0.0.0",
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
        # Optional network sink (fail-open): POST if an endpoint is configured.
        post_err = _post_event(run_id, event, skill, plugin_version)
        if post_err is None and os.environ.get(ENDPOINT_ENV, "").strip():
            return "recorded posted=ok"
        if post_err is not None:
            return f"recorded post_error={post_err}"
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
    pr.add_argument("--skill", default=None, help="skill id, e.g. gcp-to-aws")
    pr.add_argument("--plugin-version", default="0.0.0", help="plugin semver")

    sub.add_parser("status")

    args = p.parse_args(argv)
    if args.cmd == "consent":
        print(cmd_consent(args.action))
    elif args.cmd == "record":
        print(
            cmd_record(
                args.run_id,
                args.phase,
                args.event_name,
                args.status,
                args.attributes,
                args.skill,
                args.plugin_version,
            )
        )
    elif args.cmd == "status":
        print(cmd_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
