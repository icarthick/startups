"""Knowledge store loader."""

import json
import os
from pathlib import Path


def default_knowledge_dir() -> Path:
    """Resolve knowledge directory: env var > bundled package data > dev layout."""
    env = os.environ.get("ENGINE_KNOWLEDGE_DIR")
    if env:
        return Path(env)
    bundled = Path(__file__).resolve().parent / "knowledge"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2] / "knowledge"


def load_knowledge(knowledge_dir: Path) -> dict:
    """Load all .json files under knowledge_dir, indexed by relative path (stem)."""
    store = {}
    for path in knowledge_dir.rglob("*.json"):
        rel = path.relative_to(knowledge_dir).with_suffix("")
        key = str(rel)
        with open(path) as f:
            store[key] = json.load(f)
    return store
