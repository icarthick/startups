# Migration Preview

> Loaded by `phase_router` (always-active route in discover phase). Generates a
> lightweight preview signal and rough cost estimate from discovery artifacts.

---

## Step 1: Generate Preview

Call the `generate_migration_preview` MCP tool:

```
generate_migration_preview(migration_dir=$MIGRATION_DIR)
```

This reads all available discovery artifacts (`gcp-resource-inventory.json`, `ai-workload-profile.json`, `billing-profile.json`), computes:

- Complexity classification (`likely_simple`, `standard`, `complex`)
- Clarify fast-path eligibility
- Rough AWS cost range (dev-tier sizing)
- Bedrock model mapping (for AI workloads)
- Timeline hint
- Key decisions ahead

And writes `migration-preview.json` to `$MIGRATION_DIR`.

If the tool returns `status: "skipped"`, no discovery artifacts exist yet — exit cleanly.

---

## Step 2: Present Preview to User

Using the `preview` from the tool response, output this chat message:

**If `route` is `"ai_only"`:**

```
### Your AI migration at a glance *(preview — not final)*

| | |
|---|---|
| **Models detected** | [ai_summary.model_ids joined by ", "] |
| **Bedrock targets** | [for each bedrock_target: "source_model → bedrock_equivalent"] |
| **Routing** | [if ai_summary.has_multi_model_routing: gateway_type else "Direct SDK"] |
| **Monthly estimate** | Available after Estimate phase |
| **Timeline (rough)** | [timeline_hint] |
| **Decisions ahead** | [key_decisions_ahead joined by "; "] |

*Full cost breakdown in Estimate; runnable adapter code in Generate.*
AI workload detected — full Clarify recommended for best results.
```

**If `route` is `"infra"`:**

```
### Your migration at a glance *(preview — not final)*

| | |
|---|---|
| **Services** | [primary_resource_count] resources → [services_summary targets] *(standard pairings)* |
| **AWS cost (rough)** | ~$[low]-$[high]/mo [vs GCP ~$[gcp]/mo if present] *(dev-tier estimate, ±30%)* |
| **Timeline (rough)** | [timeline_hint] |
| **AI** | [if ai_detected: model IDs + "detected" else "None detected"] |
| **Decisions ahead** | [key_decisions_ahead joined by "; "] |

*Full cost breakdown in Estimate; runnable Terraform in Generate.*

[if eligible_for_clarify_fast_path: "Your stack looks straightforward — next step is 3 quick questions."]
[if ai_detected: "AI workload detected — full Clarify recommended for best results."]
```

Do NOT write this chat message to a file — chat output only.
