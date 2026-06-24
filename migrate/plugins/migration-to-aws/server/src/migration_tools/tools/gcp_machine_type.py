"""GCP machine type parser.

Parses machine type strings like 'n1-standard-4', 'n1-highmem-16',
'e2-custom-4-8192' into vCPU count and memory GB.

GCP naming convention: {family}-{class}-{vcpu} or {family}-custom-{vcpu}-{memMB}
Memory per vCPU varies by class:
  standard: 3.75 GB (n1), 4 GB (n2/e2/c3/n2d)
  highmem:  6.5 GB (n1), 8 GB (n2/e2/n2d)
  highcpu:  0.9 GB (n1), 1 GB (n2/e2/n2d)
"""

import re

# Memory-per-vCPU ratios by family and class (in GB)
_MEMORY_RATIOS: dict[str, dict[str, float]] = {
    "n1": {"standard": 3.75, "highmem": 6.5, "highcpu": 0.9},
    "n2": {"standard": 4.0, "highmem": 8.0, "highcpu": 1.0},
    "n2d": {"standard": 4.0, "highmem": 8.0, "highcpu": 1.0},
    "e2": {"standard": 4.0, "highmem": 8.0, "highcpu": 1.0},
    "c2": {"standard": 4.0, "highcpu": 1.0},
    "c2d": {"standard": 4.0, "highcpu": 1.0},
    "m1": {"ultramem": 24.0, "megamem": 14.9},
    "m2": {"ultramem": 28.0, "megamem": 14.9},
    "a2": {"highgpu": 10.0, "ultragpu": 10.0},
}

# E2 shared-core presets (fixed sizes, not following the ratio pattern)
_E2_PRESETS: dict[str, tuple[float, float]] = {
    "e2-micro": (0.25, 1.0),
    "e2-small": (0.5, 2.0),
    "e2-medium": (2.0, 4.0),
}


def parse_gcp_machine_type(machine_type: str) -> dict | None:
    """Parse a GCP machine type string into vCPU and memory_gb.

    Returns:
        {"vcpu": float, "memory_gb": float} or None if unparseable.
    """
    if not machine_type or not isinstance(machine_type, str):
        return None

    mt = machine_type.lower().strip()

    # Check E2 presets first
    if mt in _E2_PRESETS:
        vcpu, mem = _E2_PRESETS[mt]
        return {"vcpu": vcpu, "memory_gb": mem}

    # Custom: {family}-custom-{vcpu}-{memMB}
    custom_match = re.match(r"^([a-z]\w*)-custom-(\d+)-(\d+)$", mt)
    if custom_match:
        vcpu = int(custom_match.group(2))
        memory_mb = int(custom_match.group(3))
        return {"vcpu": float(vcpu), "memory_gb": round(memory_mb / 1024, 2)}

    # Standard pattern: {family}-{class}-{vcpu}
    standard_match = re.match(r"^([a-z]\w*)-([a-z]+)-(\d+)$", mt)
    if standard_match:
        family = standard_match.group(1)
        machine_class = standard_match.group(2)
        vcpu = int(standard_match.group(3))

        family_ratios = _MEMORY_RATIOS.get(family)
        if family_ratios and machine_class in family_ratios:
            memory_gb = vcpu * family_ratios[machine_class]
            return {"vcpu": float(vcpu), "memory_gb": memory_gb}

        # Unknown class but parseable vCPU — use n2-standard ratio as fallback
        return {"vcpu": float(vcpu), "memory_gb": vcpu * 4.0}

    return None
