# Gemini to Bedrock — Model Selection Guide

**Applies to:** Vertex AI Generative AI (Gemini models) → Amazon Bedrock

This file is loaded by `design-ai.md` when `ai-workload-profile.json` has `summary.ai_source` = `"gemini"` or `"both"`. It provides model mapping tables with pricing and honest competitive analysis for Gemini → Bedrock migration decisions.

Verify all pricing via AWS Pricing MCP or `references/shared/pricing-cache.md`.

**Model lifecycle:** Before recommending any Bedrock model, check `references/shared/ai-model-lifecycle.md`. Do not recommend Legacy models as primary selections for new migrations. Legacy models are annotated below where they appear.

---

## Competitive Reality (May 2026)

Gemini 3.5 Flash is now GA (May 2026) — the current flagship Flash model. Gemini 3.1 Pro is the current Pro tier. Be honest with users:

- Gemini 3.1 Pro leads 13/16 Google-reported benchmarks and 6/10 on the Artificial Analysis Intelligence Index
- ARC-AGI-2: 77.1%, SWE-Bench: 80.6% (tied with Opus 4.6 at 80.8%)
- Gemini 3.1 Pro costs $2/$12 per 1M tokens — less than half of Opus 4.6 ($5/$25), cheaper than Sonnet 4.6 ($3/$15)
- Gemini 3.5 Flash at $1.50/$9.00 is 5x more expensive than the old Gemini 2.5 Flash ($0.30/$2.50) — the Bedrock cost savings case is now much stronger for Flash-tier users

**Where Bedrock still wins:**

- Claude Sonnet 4.6 / Opus 4.x lead on real-world agentic tasks (GDPval evaluation) — the gap between benchmarks and production agent reliability is real
- Claude prompt caching (90% savings on repeated content) has no Gemini equivalent
- Claude function calling remains best-in-class for complex multi-turn tool use
- AWS ecosystem integration (Bedrock Agents, Knowledge Bases, Guardrails) has no Gemini equivalent

**Migration case by tier:**

- Gemini 3.5 Flash → Bedrock: **strong cost case** — Nova Lite is 94% cheaper; even Claude Sonnet 4.6 is comparable at $3/$15 vs $1.50/$9.00
- Gemini 3.1 Pro → Bedrock: driven by AWS consolidation, agentic reliability, or ecosystem — NOT cost or general benchmarks
- Gemini 3.1 Flash-Lite → Nova Lite/Micro: still 76-88% cheaper, strong cost case
- Gemini 2.5 Pro → Bedrock: moderate case (older model)

---

## Model Selection

For each Gemini model detected in `ai-workload-profile.json`, call:

```
recommend_bedrock_model(
  source_model_id=<model_id>,
  ai_priority=<from preferences.json ai_constraints>,
  ai_latency=<from preferences.json ai_constraints>,
  ai_token_volume=<from preferences.json ai_constraints>,
  capabilities_used=<capabilities_used from the model's profile entry>
)
```

The tool returns the best Bedrock match with pricing, savings %, assessment, capability gaps, and warnings. Use the results alongside the decision paths below to form the final recommendation.

---

## Decision Paths by Priority

### Quality-First

Gemini 3.1 Pro Preview matches or beats Opus 4.6 on most reasoning benchmarks at less than half the cost. Be transparent:

- If user needs **general reasoning/coding quality** → Gemini 3.1 Pro is competitive or better. Migration case is weak unless driven by AWS consolidation.
- If user needs **agentic reliability** (real-world multi-step tasks) → **Claude Sonnet 4.6** still leads on GDPval. This is the honest differentiator.
- If user needs **maximum reasoning on hardest problems** → **Claude Opus 4.7** ($5/$25 headline on-demand, same tier as Opus 4.6) — use the latest [Claude on Bedrock](https://aws.amazon.com/bedrock/pricing/) model card for benchmark deltas vs Gemini; Opus 4.6 remains a same-price alternative where batch or regional availability matters.

### Speed-First

Gemini Flash → **Nova Micro** (<200ms, text-only, cheapest), **Haiku 4.5** (<400ms, vision), or **Llama 4 Scout** (<300ms, cheapest capable)

### Cost-First

- Gemini Flash/Lite → **Nova Lite** (54-88% cheaper), **Nova Micro** (53-64% cheaper)
- Gemini Pro → **Llama 4 Maverick** ($0.24/$0.97, 63% cheaper than Gemini 3 Pro) or **Llama 4 Scout** ($0.17/$0.66, 75% cheaper)

### Balanced

- Gemini 3.1 Pro → **Nova 2 Pro** (-14% cost, AWS-native) or **Claude Sonnet 4.6** (+31% cost, stronger agentic reliability)
- Gemini 2.5 Pro → **Nova 2 Pro** (+10% cost, AWS-native) or **Nova Pro** (-62% cost)
- Gemini 3 Pro → **Llama 4 Maverick** (-63%), **Nova Pro** (+20%)

---

## Volume-Based Recommendations

**Low (<1M tokens/day):** Use best model for quality. Cost difference minimal at this volume.

**Medium (1-10M tokens/day):** Present cost comparison at volume. At 5M input + 2.5M output/day:

| Model             | Monthly Cost   |
| ----------------- | -------------- |
| Gemini 3 Pro      | $300           |
| Llama 4 Maverick  | $109 (-64%)    |
| Llama 4 Scout     | $75 (-75%)     |
| Nova Pro          | $360 (+20%)    |
| Claude Sonnet 4.6 | $1,575 (+425%) |

**High (10-100M tokens/day):** Cost optimization critical. Recommend multi-model tiered approach. Llama 4 Maverick/Scout or Nova for output-heavy workloads.

**Very high (>100M tokens/day):** Mandatory multi-model tiered strategy:

- Simple tasks (60% of traffic) → Nova Micro or Llama 4 Scout
- Moderate tasks (30% of traffic) → Llama 4 Maverick or Nova Pro
- Complex tasks (10% of traffic) → Claude Sonnet 4.6

---

## Cost Comparison Table (150M input + 75M output per month)

| Gemini Model                    | Monthly | Best Bedrock Match             | Monthly | Difference |
| ------------------------------- | ------- | ------------------------------ | ------- | ---------- |
| Gemini 3.1 Pro Preview ($2/$12) | $1,200  | Claude Sonnet 4.6 ($3/$15)     | $1,575  | +24%       |
| Gemini 3.1 Pro Preview ($2/$12) | $1,200  | Claude Opus 4.7 / 4.6 ($5/$25) | $2,625  | +54%       |
| Gemini 3.1 Pro Preview ($2/$12) | $1,200  | Nova 2 Pro ($1.38/$11.00)      | $1,032  | -14%       |
| Gemini 3 Pro ($0.50/$3.00)      | $300    | Llama 4 Maverick ($0.24/$0.97) | $109    | -64%       |
| Gemini 3 Pro ($0.50/$3.00)      | $300    | Llama 4 Scout ($0.17/$0.66)    | $75     | -75%       |
| Gemini 2.5 Pro ($1.25/$10)      | $938    | Nova 2 Pro ($1.38/$11.00)      | $1,032  | +9%        |
| Gemini 2.5 Pro ($1.25/$10)      | $938    | Nova Pro ($0.80/$3.20)         | $360    | -62%       |
| Gemini 2.5 Flash ($0.30/$2.50)  | $233    | Nova Lite ($0.06/$0.24)        | $27     | -88%       |
| Gemini 2.0 Flash ($0.10/$0.40)  | $45     | Nova Micro ($0.035/$0.14)      | $16     | -64%       |

_Difference column shows blended savings at a 2:1 input/output token ratio. Positive = Bedrock costs more (Gemini cheaper), negative = Bedrock cheaper._

---

## Prompt Caching (Claude Only)

Cache frequently-used system prompts for 90% cost reduction on cached portions. Example: 10K token system prompt repeated 1000x → $30 without caching, $3 with caching.

Not available on other Bedrock models. This is a significant Claude advantage for applications with heavy system prompt repetition.

---

## Feature Migration Notes

| Gemini Feature         | Bedrock Equivalent                                            | Notes                                     |
| ---------------------- | ------------------------------------------------------------- | ----------------------------------------- |
| Function calling       | Claude tools (excellent), Mistral (good)                      | Minimal changes                           |
| Structured output/JSON | Claude (excellent), Nova Pro (good)                           | Most models via prompt                    |
| Streaming              | All major models                                              | Same SSE pattern                          |
| Vision                 | Claude Sonnet/Haiku, Llama 4 Maverick                         | Multimodal parity                         |
| Context caching        | Claude prompt caching                                         | 90% savings on cached portions            |
| Audio/video input      | Nova 2 Sonic (speech), Transcribe/Rekognition (preprocessing) | Nova Sonic v1 is Legacy; use Nova 2 Sonic |
| Embeddings             | Amazon Titan Embeddings ($0.02/1M, 1536 dims)                 | Must re-embed all docs                    |
