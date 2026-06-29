// scripts/dsl-validator/checks/xtable.ts
//
// Cross-unit check: cross-table key coverage (ported from the Python validator —
// the RDS-gap catcher). Every value a PRODUCER knowledge table emits in <field>
// MUST be a key in the CONSUMER table at <path>. Catches e.g. design emitting
// db.m6g.* while estimate's rate table only had db.t4g.* (silent unpriced).
//
// Reads the JSON knowledge files directly, so it is built as a FACTORY over the
// skill root (it does not consume Units). The producer->consumer links are a
// declared list — the one spot whose own coverage is a manual list (documented).

import { type CrossUnitCheck } from "./check.ts";
import { type Finding, error } from "../findings.ts";
import { readFileSync, existsSync } from "node:fs";

interface XLink {
  readonly producer: string;
  readonly field: string;
  readonly consumer: string;
  readonly path: string; // dotted path to the consumer key-dict
}

const XTABLE_LINKS: readonly XLink[] = [
  { producer: "knowledge/design/postgres-rds-sizing.json", field: "rds_instance_class", consumer: "knowledge/estimate/aws-pricing.json", path: "rds_postgresql.instances" },
  { producer: "knowledge/design/postgres-rds-sizing.json", field: "aurora_instance_class", consumer: "knowledge/estimate/aws-pricing.json", path: "aurora_postgresql.instances" },
  { producer: "knowledge/design/redis-elasticache-sizing.json", field: "node_type", consumer: "knowledge/estimate/aws-pricing.json", path: "elasticache.nodes" },
  { producer: "knowledge/design/kafka-msk-sizing.json", field: "broker_instance_type", consumer: "knowledge/estimate/aws-pricing.json", path: "msk.brokers" },
  { producer: "knowledge/design/eks-pod-sizing.json", field: "node_type", consumer: "knowledge/estimate/aws-pricing.json", path: "eks.node_rates_monthly" },
];

function readJson(p: string): unknown | null {
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function dig(obj: unknown, path: string): unknown {
  let cur: unknown = obj;
  for (const k of path.split(".")) {
    if (cur && typeof cur === "object" && !Array.isArray(cur)) cur = (cur as Record<string, unknown>)[k];
    else return undefined;
  }
  return cur;
}

/** Build the XTABLE check bound to a skill root (it reads JSON files there). */
export function makeXtableCheck(root: string): CrossUnitCheck {
  return {
    code: "XTABLE",
    run(): readonly Finding[] {
      const findings: Finding[] = [];
      for (const link of XTABLE_LINKS) {
        const pp = `${root}/${link.producer}`;
        const cp = `${root}/${link.consumer}`;
        if (!existsSync(pp) || !existsSync(cp)) continue;
        const pdata = readJson(pp);
        const cdata = readJson(cp);
        if (pdata === null || cdata === null) continue; // JSON validity reported elsewhere

        const rows = dig(pdata, "rows");
        if (!rows || typeof rows !== "object") continue;
        const emitted = new Set<string>();
        for (const row of Object.values(rows as Record<string, unknown>)) {
          if (row && typeof row === "object" && link.field in (row as Record<string, unknown>)) {
            const v = (row as Record<string, unknown>)[link.field];
            if (typeof v === "string") emitted.add(v);
          }
        }
        const consumerMap = dig(cdata, link.path);
        const keys = consumerMap && typeof consumerMap === "object" ? new Set(Object.keys(consumerMap as object)) : new Set<string>();
        const missing = [...emitted].filter((e) => !keys.has(e)).sort();
        if (missing.length > 0) {
          findings.push(
            error(
              "XTABLE",
              `${link.producer}.${link.field} emits [${missing.join(", ")}] not present as keys in ${link.consumer}.${link.path} (consumer would look these up as missing)`,
              { file: link.consumer },
            ),
          );
        }
      }
      return findings;
    },
  };
}
