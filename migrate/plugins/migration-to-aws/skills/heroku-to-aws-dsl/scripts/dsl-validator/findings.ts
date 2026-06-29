// scripts/dsl-validator/findings.ts
//
// The common currency of the semantic + check layers. Binders and checks both
// produce Findings instead of throwing — so a single pass can collect MANY issues
// rather than stopping at the first. (The pure-syntax YAML layer still throws
// YamlParseError; everything above it accumulates Findings.)

/** error -> fails the build; warning -> advisory (fails only under --strict). */
export type Severity = "error" | "warning";

/**
 * Closed set of finding codes (the old validator's prefixes, now first-class).
 * Extend as checks are added — keeping it closed makes the full check catalog
 * visible in one place and prevents typo'd codes.
 */
export type FindingCode =
  // parse / vocabulary
  | "YAML" // malformed YAML (wrapped from YamlParseError)
  | "CLOSED_VOCAB" // an unknown _-key (Golden rule 4)
  | "BIND" // a value did not match the expected type shape
  // regions / structure
  | "REGIONS" // unit-file region grammar violation
  | "FORM1_LEAK" // a FORM-1-only key (_cases/_default/_steps) in a 2b meta block
  // loading / knowledge
  | "SUBSET" // a step file not declared by its phase
  | "USES" // a [_uses: F] marker / untagged structure-owned ref
  | "GUARD_SCOPE" // a _when guard references out-of-scope values
  | "SINGLE_OWNER" // a knowledge/template file declared more than once
  | "ORPHAN" // dangling / unreferenced knowledge file
  // cross-unit / cross-phase
  | "FRAGMENT_REF" // _id / _of_phase / file resolution
  | "PRODUCES" // _produces ownership-identity mismatch
  | "KIND_MATCH" // unit kind != frontmatter kind
  | "INTERLOCK" // re-entry guard action is not a STOP action
  | "XTABLE"; // cross-table key coverage (producer emits -> consumer keys)

export interface Location {
  readonly file: string;
  /** 1-based line; optional (some findings are file-level). */
  readonly line?: number;
  /** Optional logical path, e.g. "_preconditions[0]._on_failure". */
  readonly path?: string;
}

export interface Finding {
  readonly severity: Severity;
  readonly code: FindingCode;
  readonly message: string;
  readonly location: Location;
}

export const error = (code: FindingCode, message: string, location: Location): Finding => ({
  severity: "error",
  code,
  message,
  location,
});

export const warning = (code: FindingCode, message: string, location: Location): Finding => ({
  severity: "warning",
  code,
  message,
  location,
});

// ---------------------------------------------------------------------------
// Result<T> — a binder either yields a typed value or a list of findings.
// ---------------------------------------------------------------------------

export type Result<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly findings: readonly Finding[] };

export const ok = <T>(value: T): Result<T> => ({ ok: true, value });
export const fail = <T>(...findings: Finding[]): Result<T> => ({ ok: false, findings });

/** True if a Result failed — narrows the union for the caller. */
export function isFail<T>(r: Result<T>): r is { ok: false; findings: readonly Finding[] } {
  return !r.ok;
}
