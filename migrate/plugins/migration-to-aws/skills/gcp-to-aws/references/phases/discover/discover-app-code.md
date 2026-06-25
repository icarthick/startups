# Discover Phase: App Code Discovery

> Self-contained application code discovery sub-file. Scans for source code, detects GCP SDK imports, infers resources, flags AI signals, and if AI confidence >= 70%, extracts detailed AI workload information and generates `ai-workload-profile.json`.
> If no source code files are found, exits cleanly with no output.

**Dead-end handling:** If this file exits without producing artifacts (no source code found, or AI confidence < 70%), report to the parent orchestrator: what signals were found (if any), the confidence level, and that the user should provide Terraform files or billing exports to proceed with migration planning.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Scan Application Code

Call the `scan_app_code` MCP tool:

```
scan_app_code(project_dir=<project root>)
```

This performs a single-pass scan of all source files and dependency manifests, returning:

- `status` — "ok", "skipped" (no source files), or "error"
- `source_files_scanned` / `manifests_scanned` — counts
- `secret_files_excluded` — files skipped (potential secrets)
- `auth_exclusions` — auth SDK imports detected (excluded from migration scope)
- `gcp_imports` — GCP SDK imports with inferred service + terraform type
- `ai_signals` — AI/ML signal matches with confidence scores
- `ai_confidence` / `ai_confidence_level` — overall AI confidence (0.0–1.0)
- `ai_gate_passed` — whether confidence >= 70% (triggers Steps 2+)
- `agentic_signals` — agentic framework detections
- `agentic_classification` — `{is_agentic, framework}`
- `websocket_signals` — WebSocket/SSE pattern matches
- `gateway_signals` — LLM gateway/router detections

**If status is "skipped":** exit cleanly. Other sub-discovery files may still produce artifacts.

**Report to user:**
- Source files scanned count
- GCP services inferred (list services from `gcp_imports`)
- Auth providers detected and excluded
- AI confidence level
- Whether agentic patterns were found

**If `ai_gate_passed` is false:** Do not generate `ai-workload-profile.json` (unless one already exists from IaC discovery with `profile_source: "iac_vertex"` — leave that intact). Report signals found and confidence level. Exit.

**If `ai_gate_passed` is true:** Continue to Step 2.

---

## Step 2: Extract AI Model Details

For each AI signal found in the scan results, extract model-level details from the source files:

**From application code:**

Scan files that contained AI signals for specific model information:

- **Model identifiers** — Look for model name strings passed to constructors or API calls:

  **Gemini/Vertex AI patterns:**
  - `GenerativeModel("gemini-pro")` -> model_id: `"gemini-pro"`
  - `aiplatform.Model.list(filter='display_name="my-model"')` -> model_id: `"my-model"`
  - `TextEmbeddingModel.from_pretrained("text-embedding-004")` -> model_id: `"text-embedding-004"`
  - Look for Gemini model string patterns: `gemini-pro`, `gemini-1.5-*`, `gemini-2.0-*`, `gemini-2.5-*`, `gemini-3-*`, `gemini-3.1-*` — including versioned variants. Normalize `gemini-2.5-flash-*` variants to `model_id: "gemini-2.5-flash"`, `gemini-2.5-pro-*` to `model_id: "gemini-2.5-pro"`. Record raw string in `detection_signals`.
  - **Gemini 1.5 Legacy:** Normalize `gemini-1.5-flash*` → `model_id: "gemini-1.5-flash"` and `gemini-1.5-pro*` → `model_id: "gemini-1.5-pro"`. Set `lifecycle_status: "legacy"` and `eol_date: "2025-09-24"`.

  **OpenAI patterns:**
  - `client.chat.completions.create(model="gpt-4o")` -> model_id: `"gpt-4o"`
  - Model strings: `gpt-*`, `o1*`, `o3*`, `o4*`, `text-embedding-*`, `dall-e-*`, `gpt-image-*`, `whisper-*`, `tts-*`

  **Anthropic patterns:**
  - `anthropic.Anthropic().messages.create(model="claude-*")` -> model_id: `"claude-*"`
  - Model strings: `claude-3-*`, `claude-sonnet-*`, `claude-haiku-*`, `claude-opus-*`

- **Capabilities used** — Determine from API calls:
  - `text_generation`: `generate_content()`, `predict()`, `messages.create()`, `chat.completions.create()`
  - `streaming`: `stream=True`, async iterators
  - `function_calling`: `tools=` parameter, `function_declarations=`
  - `vision`: image bytes/URLs as input
  - `embeddings`: embedding API calls
  - `batch_processing`: batch predict calls
  - `json_mode`: `response_format={"type": "json_object"}`
  - `image_generation`: `client.images.generate()`
  - `speech_to_text`: `client.audio.transcriptions.create()`
  - `text_to_speech`: `client.audio.speech.create()`

- **Usage context** — Infer from file path, class/function names, surrounding code context.

---

## Step 2.5: Disambiguate AI Workloads by SDK Method

Split detected AI usage into distinct **workloads** — one per unique `(model_id, sdk_method, structured_output)` combination.

**Load** `data/sdk-capability-map.json` from the plugin source. If missing, halt with diagnostic.

For each AI call site:
1. Resolve SDK method name
2. Detect structured output (for methods in `structured_output_trio`)
3. Assign capability from map
4. Collapse by workload tuple
5. Generate `workload_id`: `"wl_" + sha256(model_id + "|" + sdk_method + "|" + ("structured" if structured_output else "plain"))[:6]`

---

## Step 3: Extract Agent Details (Only if `agentic_classification.is_agentic: true`)

**Skip if `is_agentic: false`.**

For each detected agent, extract:
1. **Agent identifier** (`agent_id`) — normalized snake_case
2. **File and line**
3. **Model ID** — LLM model the agent uses
4. **Tools list** — tool names attached
5. **Memory type** — `conversation_buffer`, `rag`, `none`, `unknown`
6. **Role** — one-sentence description

**Classify orchestration pattern:** `single`, `hierarchical`, `swarm`, `graph`, `sequential`, `unknown`

**Determine system-level memory:** `has_memory`, `memory_backend`

**Determine human-in-the-loop:** `has_human_in_loop`

---

## Step 3.5: Extract Tool Manifest (Only if `is_agentic: true`)

For each tool detected:
1. **Name**
2. **File and line**
3. **Transport:** `function`, `api`, `mcp`, `unknown`
4. **Auth hint:** `none`, `api_key`, `oauth`, `iam`, `unknown`
5. **Used by agents** — array of `agent_id` values

---

## Step 4: Map Integration Patterns

From the scan results (`gateway_signals`, `ai_signals`, `agentic_signals`), determine:

- **Primary SDK**: Which AI SDK is used
- **SDK version**: From dependency files
- **Frameworks**: LangChain, LlamaIndex, etc.
- **Languages**: Which languages contain AI code
- **Integration pattern**: `direct_sdk`, `framework`, `rest_api`, `mixed`
- **Gateway type**: Use `gateway_signals` from scan — `llm_router`, `api_gateway`, `voice_platform`, `framework`, `direct`, or `null`

Build **capabilities summary** — flat boolean map of active AI capabilities.

---

## Step 5: Capture Supporting Infrastructure

**Only if Terraform files were found (IaC discovery also ran):**

- AI resources: `google_vertex_ai_*`
- Supporting: service accounts, VPC connectors, Secret Manager entries, Storage buckets for models

If no Terraform, set `infrastructure: []`.

---

## Step 6: Generate ai-workload-profile.json

Load `references/shared/schema-discover-ai.md` and generate output.

### Pre-existing IaC profile (`profile_source: "iac_vertex"`)

If `$MIGRATION_DIR/ai-workload-profile.json` exists with `profile_source: "iac_vertex"`:
- Merge: set `profile_source: "merged"`
- Code wins on conflict for `models[]`, `integration`, `summary`
- `infrastructure[]`: union by resource address
- Set `sources_analyzed.application_code: true`

If no pre-existing file: generate fresh with `profile_source: "application_code"`.

**CRITICAL field names** — use EXACTLY:
`model_id`, `service`, `detected_via`, `capabilities_used`, `usage_context`, `pattern`, `gateway_type`, `capabilities_summary`, `ai_source`

**Determining `ai_source`:**
- `"gemini"` — Only Gemini/Vertex AI
- `"openai"` — Only OpenAI
- `"anthropic"` — Only Anthropic
- `"both"` — Multiple providers
- `"other"` — Traditional ML only

**Conditional sections:**
- `current_costs` — only if billing data provided
- `infrastructure` — `[]` if no Terraform
- `agentic_profile` — only if `is_agentic: true`
- `tool_manifest` — only if `agentic_profile` exists

After generating output, `phase_advance` handles phase status — do not update `.phase-status.json` here.

---

## Output Validation Checklist — ai-workload-profile.json

- `metadata.profile_source` is one of: `"application_code"`, `"iac_vertex"`, `"merged"`
- `summary.overall_confidence` matches detection confidence
- `summary.total_models_detected` matches `models` array length
- `summary.ai_source` set correctly
- Every `models[]` entry has required fields
- `integration.gateway_type` is set
- `workloads[]` present (empty array if no call sites)
- Every `workloads[].model_id` also in `models[].model_id`
- If `is_agentic: true`: `agentic_profile` and `tool_manifest` exist with required fields
- If `is_agentic: false`: `agentic_profile` and `tool_manifest` ABSENT

---

## Scope Boundary

**This phase covers Discover & Analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists in GCP. Nothing else.**
