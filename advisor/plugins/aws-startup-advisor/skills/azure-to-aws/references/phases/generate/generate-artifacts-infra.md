---
_fragment: artifacts-infra
_of_phase: generate
_contributes:
  - terraform/main.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
---

# Generate — Terraform Configurations

> **Fragment unit.** See `generate.md` for how it is composed into the phase.

Emits idiomatic replacement Terraform for the designed architecture. Where the
customer supplied IaC, its module structure and naming inform the output — that is
what the *declared intent* half of discovery was for, and it is why IaC stays a
first-class source even when live discovery is authoritative for state.

Per-domain `.tf` files (compute, data, network, security) are emitted as the design
requires. They are the **open tail**: a fragment lists in `_contributes` only what it
writes unconditionally, so the core files above are declared and the domain files are
governed by this prose and the phase's `_assert`s.

Secrets are never inlined. A Key Vault entry becomes a Secrets Manager reference,
and the value stays where it was.

## Status — skeleton (build step 1)

Wiring only; the emitters land in step 6.
