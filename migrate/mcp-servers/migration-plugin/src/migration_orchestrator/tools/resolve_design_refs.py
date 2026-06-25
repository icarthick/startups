"""Resolve which design reference files to load based on AI context.

Takes ai_source + agentic signals and returns the list of reference
files the LLM should load and follow.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_orchestrator.resolve_design_refs")


def resolve_design_refs(
    ai_source: str,
    is_agentic: bool = False,
    migration_approach: str | None = None,
    knowledge: dict | None = None,
) -> dict[str, Any]:
    """Resolve design reference files to load for AI workload design.

    Args:
        ai_source: From ai-workload-profile.json summary.ai_source
            ("gemini", "openai", "anthropic", "both", "other").
        is_agentic: Whether agentic_profile.is_agentic is true.
        migration_approach: From preferences.json ai_constraints.agentic.migration_approach
            ("retarget", "harness", "strands", "undecided"). Ignored if not agentic.
        knowledge: Knowledge store dict.

    Returns:
        Dict with files list and context notes.
    """
    routing = (knowledge or {}).get("gcp-to-aws/design-refs-routing", {})
    ai_refs = routing.get("ai_source_refs", {})
    agentic_refs = routing.get("agentic_refs", {})
    shared = routing.get("shared_refs", [])

    files = []

    # AI source routing
    source_files = ai_refs.get(ai_source, ai_refs.get("other", []))
    files.extend(source_files)

    # Agentic routing
    if is_agentic:
        approach = migration_approach or "undecided"
        agentic_files = agentic_refs.get(approach, agentic_refs.get("undecided", []))
        files.extend(agentic_files)
        files.extend(shared)

    return {
        "status": "ok",
        "files": files,
        "ai_source": ai_source,
        "is_agentic": is_agentic,
        "migration_approach": migration_approach if is_agentic else None,
    }
