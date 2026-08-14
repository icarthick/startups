#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2"]
# ///
"""
Telemetry MCP server (Phase-1 WALKING SKELETON) for the aws-startup-advisor plugin.

Scope: this is a LEARNING PROTOTYPE, not production code. It proves the Claude Code
side of the telemetry flow end to end WITHOUT a backend:

  - consent(action)  -> get | grant | revoke   (persisted opt-in flag)
  - record(event)    -> append one telemetry event to a LOCAL jsonl file
                        (NO network; no-op unless consent granted)
  - status()         -> quick human-readable state (for debugging the skeleton)

Anonymous identity only (Phase 1): a per-install UUID (installId) minted on first use.
No PII, no auth, no account. Real transport (POST to the migrate-api telemetry route)
and the richer event contract come later — see the HLD.

State lives under ~/.migration-to-aws/:
  - telemetry.json    { installId, consent: "granted"|"denied"|null, updatedAt }
  - events.jsonl      one JSON event per line (the skeleton "sink")

Design notes:
  - Tools return terse strings and print NOTHING to stdout on the happy path, so we can
    verify autoApprove keeps record/consent SILENT in the host UI.
  - record() is fail-open: any error is swallowed and reported as a soft status; it must
    never break a migration.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# --- state location ---------------------------------------------------------

STATE_DIR = Path(os.path.expanduser("~")) / ".migration-to-aws"
CONFIG_PATH = STATE_DIR / "telemetry.json"
EVENTS_PATH = STATE_DIR / "events.jsonl"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_config() -> dict[str, Any]:
    """Read the config file, tolerating a missing/corrupt file (returns a fresh dict)."""
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
    """Mint a per-install anonymous UUID once; persist it. Phase-1 principal."""
    install_id = cfg.get("installId")
    if not install_id:
        install_id = str(uuid.uuid4())
        cfg["installId"] = install_id
        cfg.setdefault("consent", None)
        cfg["updatedAt"] = _now_iso()
        _save_config(cfg)
    return install_id


def _consent_state(cfg: dict[str, Any]) -> str | None:
    return cfg.get("consent")  # "granted" | "denied" | None (never asked)


# --- server -----------------------------------------------------------------

mcp = FastMCP("telemetry")


@mcp.tool()
def consent(action: str) -> str:
    """
    Manage the user's telemetry opt-in.

    action:
      - "get"    -> report current state: granted | denied | unset
      - "grant"  -> record explicit opt-in
      - "revoke" -> record opt-out (and stop future emission)

    Returns a terse status string. Persists to ~/.migration-to-aws/telemetry.json.
    Call "get" at skill start; if it returns "unset", present the opt-in prompt, then
    call "grant" or "revoke" with the user's choice.
    """
    cfg = _load_config()
    _ensure_install_id(cfg)
    act = (action or "").strip().lower()

    if act == "get":
        state = _consent_state(cfg) or "unset"
        return f"consent={state}"
    if act == "grant":
        cfg["consent"] = "granted"
        cfg["updatedAt"] = _now_iso()
        _save_config(cfg)
        return "consent=granted"
    if act == "revoke":
        cfg["consent"] = "denied"
        cfg["updatedAt"] = _now_iso()
        _save_config(cfg)
        return "consent=denied"
    return "error=unknown_action (use get|grant|revoke)"


@mcp.tool()
def record(
    run_id: str,
    phase: str,
    event_name: str,
    status: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> str:
    """
    Record ONE telemetry event for the current migration.

    Appends to the local sink (~/.migration-to-aws/events.jsonl). NO network in the
    skeleton. NO-OP (returns silently) unless consent has been granted — so it is safe
    to call unconditionally at every phase boundary.

    Args:
      run_id:     per-migration UUID (the join key; minted at migration start)
      phase:      the completed phase (discover|clarify|design|estimate|generate|...)
      event_name: the discrete event (e.g. phase.completed, phase.failed)
      status:     optional (SUCCESS|PARTIAL|ABORTED|FAILED|SKIPPED)
      attributes: optional dict of enum/scalar values (pricing_source, outcome, ...)

    Fail-open: any error is swallowed; never raises, never blocks the migration.
    """
    try:
        cfg = _load_config()
        install_id = _ensure_install_id(cfg)
        if _consent_state(cfg) != "granted":
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
        if attributes:
            event["attributes"] = attributes

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a") as f:
            f.write(json.dumps(event) + "\n")
        return "recorded"
    except Exception as e:  # fail-open
        return f"soft_error={type(e).__name__}"


@mcp.tool()
def status() -> str:
    """Human-readable skeleton state (for debugging): consent, installId, event count."""
    cfg = _load_config()
    install_id = cfg.get("installId", "unset")
    consent_state = _consent_state(cfg) or "unset"
    count = 0
    try:
        if EVENTS_PATH.exists():
            count = sum(1 for _ in EVENTS_PATH.open())
    except Exception:
        pass
    return f"consent={consent_state} installId={install_id} events={count} sink={EVENTS_PATH}"


if __name__ == "__main__":
    mcp.run()
