"""Knowledge store loader.

Loads all JSON knowledge files from the knowledge/ directory at startup,
indexes them by relative path (stem) for fast lookup by tools.
"""

import json
from pathlib import Path


def default_knowledge_dir() -> Path:
    """Resolve knowledge directory: env var > bundled package data > dev layout."""
    import os
    env = os.environ.get("MIGRATION_KNOWLEDGE_DIR")
    if env:
        return Path(env)
    # Bundled inside installed package (knowledge/ next to __init__.py)
    bundled = Path(__file__).resolve().parent / "knowledge"
    if bundled.is_dir():
        return bundled
    # Dev layout (knowledge/ two levels up from src/migration_knowledge/)
    return Path(__file__).resolve().parents[2] / "knowledge"


def load_knowledge(knowledge_dir: Path) -> dict:
    """Load all .json files under knowledge_dir, indexed by relative path (stem)."""
    store = {}
    for path in knowledge_dir.rglob("*.json"):
        if path.parent.name == "schemas":
            continue  # schemas are for validation, not runtime
        rel = path.relative_to(knowledge_dir).with_suffix("")
        key = str(rel)  # e.g. "universal/archetypes/container/definition"
        with open(path) as f:
            store[key] = json.load(f)
    return store
