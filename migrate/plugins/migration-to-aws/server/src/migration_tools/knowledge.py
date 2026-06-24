"""Knowledge store loader.

Loads all JSON knowledge files from the knowledge/ directory at startup,
indexes them by relative path (stem) for fast lookup by tools.
"""

import json
from pathlib import Path


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
