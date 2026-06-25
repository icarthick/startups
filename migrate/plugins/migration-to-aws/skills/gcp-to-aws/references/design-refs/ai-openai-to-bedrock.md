# OpenAI to Bedrock — Model Selection Guide

**Applies to:** OpenAI SDK usage detected in GCP-hosted applications → Amazon Bedrock

This file is loaded by `design-ai.md` when `ai-workload-profile.json` has `summary.ai_source` = `"openai"` or `"both"`. It provides model mapping tables with pricing and honest competitive analysis for OpenAI → Bedrock migration decisions.

Many GCP-hosted applications use OpenAI's API rather than Vertex AI. This guide covers that migration path.

Verify all pricing via AWS Pricing MCP or `references/shared/pricing-cache.md`. Uses OpenAI Standard tier pricing.

**Model lifecycle:** Before recommending any Bedrock model, check `references/shared/ai-model-lifecycle.md`. Do not recommend Legacy models as primary selections for new migrations. Legacy models are annotated below where they appear.

---

## Key Insight: The Landscape Has Changed (April 2026)

**It is no longer "Bedrock is always cheaper."** It depends on the model.

- **Bedrock cheaper:** GPT-5.5 flagship (17% cheaper output via Opus 4.6), Nova Lite vs Mini models (85-94%), Nova Micro vs Nano (65-87%), Nova 2 Pro vs Pro models (90-95%), DeepSeek-R1 vs o3 (32%)
- **OpenAI cheaper:** GPT-5.4 (5%), GPT-5.2 (50%), GPT-5.1/5 (40%), GPT-4.1 (43%), GPT-4o (29%), o4-mini/o3-mini/o1-mini (69%)

> **GPT-5.5 note (April 23, 2026):** GPT-5.5 doubled pricing to $5/$30 per MTok vs GPT-5.4's $2.50/$15. Claude Opus 4.6 at $5/$25 now matches on input and is **17% cheaper on output**. This reverses the GPT-5.4 dynamic where OpenAI was cheaper — at the GPT-5.5 tier, Bedrock wins on cost. GPT-5.5 uses 40% fewer output tokens on coding tasks (per OpenAI), partially offsetting the price hike for Codex-style workloads.

---

## Model Selection

For each OpenAI model detected in `ai-workload-profile.json`, call:

```
recommend_bedrock_model(
  source_model_id=<model_id>,
  ai_priority=<from preferences.json ai_constraints>,
  ai_latency=<from preferences.json ai_constraints>,
  ai_token_volume=<from preferences.json ai_constraints>,
  capabilities_used=<capabilities_used from the model's profile entry>
)
```

The tool returns the best Bedrock match with pricing, savings %, assessment (strong_migrate / recommend_stay), capability gaps, and warnings. Use the results alongside the decision framework below to form the final recommendation.

**If `capability_gaps` is non-empty:** The tool has identified features the workload uses that Bedrock lacks. Present these honestly and consult the decision framework below.

**If `unresolved_factors` is non-empty:** The tool couldn't fully assess — use the qualitative factors below to enrich.

---

## Migration Decision Framework

**Migrate to Bedrock if:**

- Using GPT-5.5 flagship → Bedrock 17% cheaper on output via Opus 4.6 ($5/$25 vs $5/$30); Sonnet 4.6 is 53% cheaper
- Using Pro/expensive models (GPT-5.5 Pro, GPT-5.4 Pro, o1-pro) → 87-98% savings via Nova 2 Pro
- Using Mini/Nano models at high volume → 87-94% savings via Nova Lite/Micro
- Using legacy GPT-4/3.5 → 42-82% savings
- Need AWS infrastructure integration
- Need prompt caching (Claude only, 90% savings on cached content)
- Using o3 for reasoning → DeepSeek-R1 on Bedrock is 32% cheaper
- Want to stay on OpenAI models → gpt-oss on Bedrock (same models, AWS infrastructure)

**Consider staying on OpenAI if:**

- Using GPT-5.5 for omnimodal (audio/video) → Claude is text+image only; GPT-5.5 has native audio/video
- Using GPT-5.4 flagship → only 5% cheaper than Sonnet 4.6; marginal either way
- Using mid-tier flagships (GPT-5, GPT-4.1, o3, o4-mini) → OpenAI 29-69% cheaper
- Low volume (<$500/mo) where absolute savings are small
- Heavily integrated with OpenAI ecosystem (Assistants API, gpt-image, Whisper, Realtime)
- Need Realtime API (no Bedrock equivalent)

**Analyze carefully:** Calculate actual token usage x model-specific pricing. Small % differences matter at scale.

---

## Feature Migration

| OpenAI Feature       | Bedrock Equivalent                       | Notes                                                                                                                          |
| -------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| OpenAI SDK (direct)  | Mantle OpenAI-compat endpoints           | Zero code changes — set `OPENAI_BASE_URL` + API key + model ID                                                                 |
| Function calling     | Claude tools (excellent, similar format) | Minimal changes (works via Mantle or Converse API)                                                                             |
| Streaming            | All major models                         | Verify gateway format                                                                                                          |
| Vision (GPT-4V)      | Claude Sonnet/Haiku, Llama 4 Maverick    | 70-95% cheaper                                                                                                                 |
| Embeddings (ada-002) | Titan Embeddings ($0.02/1M, 1536 dims)   | Must re-embed all docs                                                                                                         |
| DALL-E / gpt-image   | Nova Canvas ($0.04-$0.08/img)            | DALL-E EOL May 12, 2026; OpenAI replacement is gpt-image-1.5; Titan Image Gen v2 is Legacy (EOL Jun 30, 2026); use Nova Canvas |
| Whisper (STT)        | Amazon Transcribe ($0.024/min)           | 4x more expensive but more features                                                                                            |
| TTS                  | Amazon Polly                             | Different pricing model                                                                                                        |
| Assistants API       | See Assistants API decision tree below   | Path depends on which Assistants features are used — see decision tree                                                         |
| JSON mode            | Claude (excellent), Nova Pro (good)      | Most models via prompt                                                                                                         |
| Realtime API         | No equivalent                            | Stay on OpenAI for this                                                                                                        |

---

## Common Migration Paths

### OpenAI SDK → Mantle (minimal code changes)

If the application uses the OpenAI Python/JS SDK directly (`from openai import OpenAI` / `new OpenAI()`), Bedrock's [Mantle OpenAI-compatible endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html) allow migration with minimal code changes — primarily environment variables plus a model string swap:

1. Set `OPENAI_BASE_URL=https://bedrock-mantle.{region}.api.aws/v1`
2. Set `OPENAI_API_KEY=<bedrock-api-key>` — use a Bedrock API key, **not** your existing OpenAI API key
3. Change model string (e.g., `gpt-5.4` → `anthropic.claude-sonnet-4-6` or `openai.gpt-oss-120b`)

**Hard gates before recommending Mantle:**

- **Model compatibility:** Verify the selected Bedrock model supports the Responses API — [check API compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html). Not all models do. Do not recommend Mantle Responses API unless the target model is confirmed compatible.
- **Region availability:** Mantle is available in 13 regions (us-east-1, us-east-2, us-west-2, ap-northeast-1, ap-south-1, ap-southeast-2, ap-southeast-3, eu-central-1, eu-west-1, eu-west-2, eu-south-1, eu-north-1, sa-east-1). If the target region is outside this list, do not recommend Mantle — use the boto3 Converse API path instead.

Supports Chat Completions API, Responses API, streaming, and stateful conversations.

**Responses API capabilities (when stateful conversations matter):**

- **Stateful conversation management** — Bedrock rebuilds context automatically; no need to pass full conversation history on each request
- **Async / long-running inference** — background processing for workloads that exceed typical request timeouts (useful for complex agentic tasks)
- **Streaming + non-streaming** — both modes supported via the same endpoint

### Assistants API → Migration Decision Tree

Assistants API and Responses API are different surfaces. Do not treat all Assistants API usage as an env-var-only migration. Apply this decision tree:

**1. App already uses OpenAI Responses API** (`responses.create`)
→ Mantle is the cleanest path. Env var swap + model string change. Minimal code changes.

**2. App uses Assistants API only for stateful multi-turn conversation** (no hosted tools, no file search, no code interpreter, no persistent Assistant objects, no complex run lifecycle)
→ Mantle Responses API is viable. Requires migrating from `threads`/`runs` calls to `responses.create` — this is a small API migration (days), not a full redesign. Not a zero-code-change swap.

**3. App uses Assistants API with simple hosted tools** (function calling only, no file search or code interpreter)
→ Mantle Responses API with tool use is viable. Moderate code migration (1-2 weeks) to adapt tool definitions and run lifecycle.

**4. App uses Assistants API with file search, vector stores, code interpreter, persistent Assistant objects, or complex run lifecycle management**
→ Do not recommend Mantle. Evaluate: Bedrock Agents (sessions, action groups, knowledge bases) for full agentic replacement (2-4 week migration), or app-managed orchestration if the team prefers to own state.

**When to prefer Converse API over Mantle:** If you need Bedrock-specific features (Guardrails, Knowledge Bases, prompt caching, Bedrock Agents integration) or your target region doesn't have Mantle. Mantle is the fastest path; Converse API is the most feature-complete path.

### GPT-5.4 → Claude Sonnet 4.6

Near price parity (~5% difference). Migration case is driven by AWS consolidation, agentic reliability, or prompt caching — not cost. Both have ~200K+ context. Low risk.

### GPT-5.4 Mini/Nano → Nova Lite/Micro

87-94% savings. Strong cost case at any volume. Nova Lite (300K context) covers most GPT-5.4 Mini use cases.

### GPT-4/4 Turbo → Claude Sonnet 4.6

70-90% savings, similar or better quality, longer context (200K vs 128K). Low risk.

### GPT-3.5 Turbo → Llama 4 Maverick

Similar cost, dramatically better quality, 1M context (vs 16K).

### GPT-4 → Multi-Model (high spend)

Tier by complexity: simple → Nova Micro/Llama 4 Scout (60%), moderate → Llama 4 Maverick/Nova Pro (30%), complex → Claude Sonnet (10%). 85-95% savings.

### Pro models → Nova 2 Pro

83-98% savings. Strong migration case at any volume. (Nova Premier v1 is Legacy — use Nova 2 Pro instead.)

---

## Volume-Based Recommendations

**Low (<1M tokens/day):** Use best model for quality. Cost difference minimal.

**Medium (1-10M tokens/day):** Present cost comparison at volume. At 5M input + 2.5M output/day, evaluate per-model economics carefully.

**High (10-100M tokens/day):** Multi-model tiered approach recommended. Route by task complexity.

**Very high (>100M tokens/day):** Mandatory tiering:

- Simple tasks (60%) → Nova Micro or Llama 4 Scout
- Moderate tasks (30%) → Llama 4 Maverick or Nova Pro
- Complex tasks (10%) → Claude Sonnet 4.6

---

## OpenAI Pricing Tiers

OpenAI offers 4 tiers: Batch (50% off, 24hr), Flex (30-50% off, higher latency), Standard (baseline), Priority (2x, lowest latency). This guide uses Standard tier for comparison.
