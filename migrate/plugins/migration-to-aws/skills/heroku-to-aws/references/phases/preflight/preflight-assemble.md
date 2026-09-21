---
_assemble: assemble-preflight
_of_phase: preflight
_reads:
  - check (fragment contribution)
_produces:
  - preflight-report.json
---

# Preflight — Assemble preflight-report.json

> **Assembler unit.** Combines the check fragment's output into
> `preflight-report.json`, presents a summary to the user, updates
> `.phase-status.json`, and returns control to the Estimate→Generate flow.

---

## Step 1: Write `preflight-report.json`

Write to `$MIGRATION_DIR/preflight-report.json`:

```json
{
  "status": "<pass | warn | blocked>",
  "region": "<preferences.region>",
  "services_checked": <count of services[] in aws-design.json>,
  "blockers": [
    {
      "service_id": "<string>",
      "aws_service": "<string>",
      "issue": "<instance_not_in_region | quota_exceeded>",
      "detail": "<string>",
      "remediation": "<string>",
      "quota_source": "<string or null>"
    }
  ],
  "quota_items": [
    {
      "service_id": "<string>",
      "aws_service": "<string>",
      "issue": "<quota_near_limit | needs_manual_check>",
      "detail": "<string>",
      "remediation": "<string>",
      "quota_source": "<string or null>",
      "needs_manual_check": "<true | false>"
    }
  ],
  "checked_at": "<ISO 8601 timestamp>"
}
```

`blockers` and `quota_items` are the lists accumulated by `preflight-check.md`.
`status` is the roll-up derived at the end of Step 4 in that fragment.

---

## Step 2: Present summary to user

Present a concise summary:

- **Status badge**: `✅ PASS`, `⚠️ WARN`, or `🚫 BLOCKED`
- **Region checked**: `preferences.region`
- **Services checked**: count
- If `blockers[]` non-empty: list each blocker's `detail` + `remediation`
- If `quota_items[]` non-empty: list each item's `detail` + `remediation`
- If `status == "pass"`: "All proposed services are available in the target
  region and within default quotas."

Close with:

```
You can now proceed to Generate. Any blockers above should be resolved
before deployment (request quota increases via the AWS Service Quotas
console, or adjust instance types in the what-if workshop).

[A] Proceed to Generate
```

---

## Step 3: Update `.phase-status.json`

1. Read `$MIGRATION_DIR/.phase-status.json`.
2. Set `phases.preflight` → `"completed"` (sidebar resolved — participated).
3. Set `current_phase` → `"generate"`.
4. Update `last_updated` → now.
5. Write the full file.

The participation signal for this sidebar is the presence of
`preflight-report.json` — `"completed"` means resolved (offered and acted on),
not necessarily that blockers were found. A clean `pass` is also `"completed"`.
