// scripts/dsl-validator/types/on-error-table.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_on_error" (lines 158-165),
// §"ERROR ACTIONS" (349-365). Resolves the Type-1 deferred documentation-table
// sibling.
//
// The phase/unit `_on_error:` block. NOT a carrier of one ErrorAction — it is a
// REFERENCE TABLE mapping the error-action names this unit uses to their
// documented {effect, status}. "NOT executed ... treat it as documentation."
// The canonical ERROR ACTIONS section (ERROR_ACTION_SEMANTICS) is authoritative
// over it.
//
// Pure types only. Checks (keys are valid ErrorActionKind; each {effect, status}
// matches the canonical semantics — the drift catch) live in the check layer.

import { type ErrorActionKind } from "./error-action.ts";

export interface OnErrorTableEntry {
  readonly effect: string;
  readonly status: string;
}

export interface OnErrorTable {
  /** A PARTIAL map — a unit documents only the actions it uses. */
  readonly entries: Partial<Record<ErrorActionKind, OnErrorTableEntry>>;
}
