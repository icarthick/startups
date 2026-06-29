// scripts/dsl-validator/node-shims.d.ts
//
// Minimal ambient declarations for the slice of Node's stdlib the validator uses.
// We run under Node 24 (these resolve at runtime); this file exists ONLY so `tsc`
// can type-check without pulling all of @types/node — keeping the zero-dependency
// property (same philosophy as the hand-written YAML parser). Extend as needed.

declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
  export function existsSync(path: string): boolean;
  export function readdirSync(path: string): string[];
  export function readdirSync(
    path: string,
    options: { withFileTypes: true },
  ): { name: string; isDirectory(): boolean }[];
}

declare const process: {
  readonly argv: string[];
  exit(code?: number): never;
};
