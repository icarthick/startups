"""scan_tf_references — scan .tf files for resource blocks and cross-references."""

import re
from pathlib import Path

_RESOURCE_RE = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
_REF_RE = re.compile(r'([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\.([a-z][a-z0-9_]*)')
_UNRESOLVED_RE = re.compile(r'\b(var\.[a-z_][a-z0-9_.]*|local\.[a-z_][a-z0-9_.]*|module\.[a-z_][a-z0-9_.]*)')
_FOR_EACH_RE = re.compile(r'for_each\s*=\s*(.+)')
_COUNT_RE = re.compile(r'count\s*=\s*')


def _strip_comments(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'(#|//).*', '', text)
    return text


def _extract_block_body(text: str, start: int) -> str:
    depth, i = 0, start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return text[start:]


def scan_tf_references(project_directory: str) -> dict:
    """Scan .tf files for resource blocks and cross-references."""
    tf_files = sorted(Path(project_directory).glob("*.tf"))
    resources_found = []
    file_map = {}
    all_addresses = set()
    raw_edges = []
    unresolved = []
    for_each_resources = []

    # First pass: discover all resources
    file_contents = {}
    for tf in tf_files:
        content = _strip_comments(tf.read_text())
        file_contents[tf.name] = content
        for m in _RESOURCE_RE.finditer(content):
            addr = f"{m.group(1)}.{m.group(2)}"
            all_addresses.add(addr)
            file_map[addr] = tf.name

    # Second pass: extract references
    for filename, content in file_contents.items():
        for m in _RESOURCE_RE.finditer(content):
            rtype, rname = m.group(1), m.group(2)
            addr = f"{rtype}.{rname}"
            body_start = m.end() - 1  # points to '{'
            body = _extract_block_body(content, body_start)

            has_for_each = bool(_FOR_EACH_RE.search(body))
            has_count = bool(_COUNT_RE.search(body))

            resources_found.append({
                "address": addr, "file": filename,
                "has_for_each": has_for_each, "has_count": has_count,
            })

            if has_for_each:
                fe_match = _FOR_EACH_RE.search(body)
                for_each_resources.append({
                    "address": addr,
                    "iterator_expr": fe_match.group(1).strip(),
                    "file": filename,
                })

            # Find resource references
            seen_edges = set()
            for ref_match in _REF_RE.finditer(body):
                target = f"{ref_match.group(1)}.{ref_match.group(2)}"
                if target == addr:
                    continue
                if target in all_addresses and target not in seen_edges:
                    seen_edges.add(target)
                    raw_edges.append({"from": addr, "to": target, "file": filename, "type": "reference"})

            # Find unresolved references
            for u_match in _UNRESOLVED_RE.finditer(body):
                unresolved.append({"in_resource": addr, "reference": u_match.group(1), "file": filename})

    return {
        "resources_found": resources_found,
        "edges": raw_edges,
        "file_map": file_map,
        "unresolved_references": unresolved,
        "for_each_resources": for_each_resources,
        "summary": {
            "files_scanned": len(tf_files),
            "resources_found": len(resources_found),
            "edges_found": len(raw_edges),
            "unresolved": len(unresolved),
        },
    }
