"""Scan application source code for GCP SDK imports, AI signals, and agentic patterns.

Performs Steps 0-4 of discover-app-code.md in a single pass:
- Finds source files and dependency manifests
- Excludes secret files
- Detects auth SDK imports (excluded from migration)
- Detects GCP SDK imports → inferred resources
- Flags AI/ML signals from imports and dependencies
- Detects agentic framework patterns
- Detects WebSocket signals
- Detects LLM gateway/router patterns
- Computes AI confidence gate
"""

import fnmatch
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("migration_orchestrator.scan_app_code")

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".scala", ".kt", ".rs"}
MANIFEST_NAMES = {
    "requirements.txt", "setup.py", "pyproject.toml", "Pipfile",
    "package.json", "package-lock.json", "yarn.lock",
    "go.mod", "go.sum", "pom.xml", "build.gradle",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".terraform"}


def _should_exclude(path: Path, exclusion_patterns: list[str]) -> bool:
    """Check if a file matches any secret exclusion pattern."""
    name = path.name
    for pattern in exclusion_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _scan_files(project_dir: Path, exclusion_patterns: list[str]) -> tuple[list[Path], list[Path], list[str]]:
    """Scan for source files and manifests, returning (sources, manifests, excluded)."""
    sources = []
    manifests = []
    excluded = []

    for path in project_dir.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if _should_exclude(path, exclusion_patterns):
            excluded.append(str(path.relative_to(project_dir)))
            continue
        if path.suffix in SOURCE_EXTENSIONS:
            sources.append(path)
        elif path.name in MANIFEST_NAMES:
            manifests.append(path)

    return sources, manifests, excluded


def _read_file_safe(path: Path) -> str:
    """Read file with fallback encoding."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def _detect_auth(content: str, file_path: str, auth_patterns: list[dict]) -> list[dict]:
    """Detect auth SDK imports."""
    found = []
    for entry in auth_patterns:
        for imp in entry["imports"]:
            if imp in content:
                found.append({"provider": entry["provider"], "file": file_path, "import": imp})
                break
    return found


def _detect_gcp_imports(content: str, file_path: str, gcp_patterns: list[dict]) -> list[dict]:
    """Detect GCP SDK imports → inferred services."""
    found = []
    for entry in gcp_patterns:
        imp = entry["import"]
        # Match both "google.cloud.storage" and "from google.cloud import storage"
        if imp in content:
            found.append({
                "file": file_path,
                "import": imp,
                "service": entry["service"],
                "tf_type": entry["tf_type"],
                "confidence": 0.70,
            })
        elif "." in imp:
            # Handle "from google.cloud import storage" for "google.cloud.storage"
            parts = imp.rsplit(".", 1)
            if len(parts) == 2:
                alt = f"from {parts[0]} import {parts[1]}"
                if alt in content:
                    found.append({
                        "file": file_path,
                        "import": imp,
                        "service": entry["service"],
                        "tf_type": entry["tf_type"],
                        "confidence": 0.70,
                    })
    return found


def _detect_ai_signals(content: str, file_path: str, ai_config: dict) -> list[dict]:
    """Detect AI/ML signals from imports and code patterns."""
    found = []
    for entry in ai_config.get("import_patterns", []):
        for pattern in entry["patterns"]:
            if pattern in content:
                # Check requires_context if specified
                if "requires_context" in entry:
                    if not any(ctx in content for ctx in entry["requires_context"]):
                        continue
                found.append({
                    "id": entry["id"],
                    "file": file_path,
                    "pattern": pattern,
                    "confidence": entry["confidence"],
                })
                break
    return found


def _detect_ai_in_manifests(content: str, file_path: str, ai_config: dict) -> list[dict]:
    """Detect AI dependencies in manifest files."""
    found = []
    for entry in ai_config.get("dependency_patterns", []):
        for pkg in entry["packages"]:
            if pkg in content:
                found.append({"id": entry["id"], "file": file_path, "package": pkg})
                break
    return found


def _detect_agentic(content: str, file_path: str, agentic_config: dict) -> list[dict]:
    """Detect agentic framework signals."""
    found = []
    for entry in agentic_config.get("import_patterns", []):
        import_match = any(p in content for p in entry["patterns"])
        code_match = any(p in content for p in entry.get("code_patterns", []))
        if import_match or code_match:
            found.append({
                "id": entry["id"],
                "framework": entry["framework"],
                "file": file_path,
                "confidence": entry["confidence"],
            })
    return found


def _detect_agentic_in_manifests(content: str, file_path: str, agentic_config: dict) -> list[dict]:
    """Detect agentic framework dependencies."""
    found = []
    for entry in agentic_config.get("dependency_patterns", []):
        for pkg in entry["packages"]:
            if pkg in content:
                found.append({"id": entry["id"], "file": file_path, "package": pkg})
                break
    return found


def _detect_websocket(content: str, file_path: str, ws_patterns: list[str]) -> list[dict]:
    """Detect WebSocket/SSE signals."""
    found = []
    for pattern in ws_patterns:
        if pattern in content:
            found.append({"file": file_path, "pattern": pattern})
    return found


def _detect_gateway(content: str, file_path: str, gateway_config: dict) -> list[dict]:
    """Detect LLM gateway/router patterns."""
    found = []
    for entry in gateway_config.get("import_patterns", []):
        for pattern in entry["patterns"]:
            if pattern in content:
                found.append({
                    "id": entry["id"],
                    "gateway_type": entry["gateway_type"],
                    "file": file_path,
                    "pattern": pattern,
                })
                break
    # Env var content matches
    for entry in gateway_config.get("env_var_patterns", []):
        if "vars" in entry:
            for var in entry["vars"]:
                if var in content:
                    found.append({
                        "id": entry["id"],
                        "gateway_type": entry["gateway_type"],
                        "file": file_path,
                        "pattern": var,
                    })
                    break
        if "content_match" in entry:
            if entry["content_match"] in content:
                found.append({
                    "id": entry["id"],
                    "gateway_type": entry["gateway_type"],
                    "file": file_path,
                    "pattern": entry["content_match"],
                })
    return found


def _compute_ai_confidence(ai_signals: list[dict]) -> tuple[float, str]:
    """Compute overall AI confidence from signal collection."""
    if not ai_signals:
        return 0.0, "none"

    signal_ids = {s["id"] for s in ai_signals}
    strong_signals = {"vertex_ai", "gemini", "openai", "anthropic"}
    medium_signals = {"bigquery_ml", "embeddings_rag"}

    strong_count = len(signal_ids & strong_signals)
    if strong_count >= 2:
        return 0.95, "very_high"
    if strong_count == 1:
        return 0.90, "high"
    if signal_ids & medium_signals:
        return 0.65, "medium"
    # Specialized AI (vision, speech, etc.)
    return 0.85, "high"


def _classify_agentic(agentic_signals: list[dict]) -> dict:
    """Classify agentic status from signals."""
    if not agentic_signals:
        return {"is_agentic": False, "framework": None}

    # Pick framework with most signals
    from collections import Counter
    frameworks = Counter(s["framework"] for s in agentic_signals if "framework" in s)
    if frameworks:
        top_framework = frameworks.most_common(1)[0][0]
        return {"is_agentic": True, "framework": top_framework}

    return {"is_agentic": True, "framework": "custom"}


def scan_app_code(project_dir: str, knowledge: dict) -> dict[str, Any]:
    """Scan application code for GCP imports, AI signals, and agentic patterns.

    Single-pass scan of source files and dependency manifests. Returns
    structured results for each detection category.

    Args:
        project_dir: Absolute path to the project root.
        knowledge: Knowledge store dict (loaded from JSON files).

    Returns:
        Structured dict with: source_files, auth_exclusions, gcp_imports,
        ai_signals, agentic_signals, websocket_signals, gateway_signals,
        ai_confidence, agentic_classification.
    """
    root = Path(project_dir)
    if not root.is_dir():
        return {"status": "error", "reason": f"Directory not found: {project_dir}"}

    # Load knowledge
    secret_excl = knowledge.get("app-code/secret-exclusions", {}).get("patterns", [])
    auth_config = knowledge.get("app-code/auth-exclusions", {}).get("patterns", [])
    gcp_config = knowledge.get("app-code/gcp-sdk-imports", {}).get("patterns", [])
    ai_config = knowledge.get("app-code/ai-signals", {})
    agentic_config = knowledge.get("app-code/agentic-signals", {})
    ws_patterns = knowledge.get("app-code/websocket-signals", {}).get("patterns", [])
    gateway_config = knowledge.get("app-code/gateway-signals", {})

    # Step 0: Scan files
    sources, manifests, excluded = _scan_files(root, secret_excl)

    if not sources and not manifests:
        return {"status": "skipped", "reason": "No source code or dependency manifests found"}

    # Single pass through all files
    all_auth = []
    all_gcp = []
    all_ai = []
    all_agentic = []
    all_ws = []
    all_gateway = []

    for path in sources:
        content = _read_file_safe(path)
        if not content:
            continue
        rel = str(path.relative_to(root))

        all_auth.extend(_detect_auth(content, rel, auth_config))
        all_gcp.extend(_detect_gcp_imports(content, rel, gcp_config))
        all_ai.extend(_detect_ai_signals(content, rel, ai_config))
        all_agentic.extend(_detect_agentic(content, rel, agentic_config))
        all_ws.extend(_detect_websocket(content, rel, ws_patterns))
        all_gateway.extend(_detect_gateway(content, rel, gateway_config))

    for path in manifests:
        content = _read_file_safe(path)
        if not content:
            continue
        rel = str(path.relative_to(root))

        all_ai.extend(_detect_ai_in_manifests(content, rel, ai_config))
        all_agentic.extend(_detect_agentic_in_manifests(content, rel, agentic_config))

    # Step 4: Compute gates
    ai_confidence, confidence_level = _compute_ai_confidence(all_ai)
    agentic_classification = _classify_agentic(all_agentic)

    # Deduplicate GCP imports by service
    seen_services = set()
    deduped_gcp = []
    for imp in all_gcp:
        if imp["service"] not in seen_services:
            seen_services.add(imp["service"])
            deduped_gcp.append(imp)

    return {
        "status": "ok",
        "source_files_scanned": len(sources),
        "manifests_scanned": len(manifests),
        "secret_files_excluded": excluded,
        "auth_exclusions": all_auth,
        "gcp_imports": deduped_gcp,
        "ai_signals": all_ai,
        "ai_confidence": ai_confidence,
        "ai_confidence_level": confidence_level,
        "ai_gate_passed": ai_confidence >= 0.70,
        "agentic_signals": all_agentic,
        "agentic_classification": agentic_classification,
        "websocket_signals": all_ws,
        "gateway_signals": all_gateway,
    }
