// scripts/dsl-validator/binders/orientation.ts
//
// Body binder: the ## Orientation prose -> Orientation. Trivial wrap; the
// non-normative / recap-with-pointer rule is a check, not a bind concern.

import { type Orientation } from "../types/orientation.ts";
import { type Location, type Result, ok } from "../findings.ts";

export function bindOrientation(prose: string, _loc: Location): Result<Orientation> {
  return ok({ prose });
}
