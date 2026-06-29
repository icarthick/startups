// scripts/dsl-validator/types/step.ts
//
// Tier 3 sub-document type. Source: INTERPRETER.md §"FORM 2b" (lines 415-420),
// §"Unit file regions" (395-425), §"[_uses:] prose marker" (127-145).
//
// ONE `## Step: <id>` section — the unit's executable procedure unit. In FORM 2b
// a step is: the heading id, an OPTIONAL ```meta``` block (Type 8), then reason
// prose ("the body prose IS the reason" — authoritative for HOW, Golden rule 3).
//
// `uses` is a DERIVED field: the [_uses: F] markers extracted from `prose`. It is
// carried on Step deliberately so the marker<->meta binding is a first-class
// STRUCTURAL check (the whole reason the marker exists), not a regex buried in the
// check layer. `prose` remains the verbatim instruction.
//
// Pure types only. Checks (id uniqueness within unit; every uses[] ∈
// meta.knowledge∪templates; untagged structure-owned refs in prose) live in the
// check layer.

import { type Meta } from "./meta.ts";

export interface Step {
  /** From the `## Step: <id>` heading. Unique within the unit (a unit-level check). */
  readonly id: string;
  /** The optional ```meta``` block — the step's machine contract. */
  readonly meta?: Meta;
  /** The verbatim reason prose — authoritative for HOW (Golden rule 3). */
  readonly prose: string;
  /**
   * The `[_uses: F]` markers extracted from `prose` — the checkable projection
   * binding prose file-references back to `meta` knowledge/templates. Empty if the
   * prose tags nothing.
   */
  readonly uses: readonly string[];
}
