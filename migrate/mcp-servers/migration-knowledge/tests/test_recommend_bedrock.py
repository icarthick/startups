"""Tests for recommend_bedrock_model tool."""

from pathlib import Path

import pytest

from migration_knowledge.knowledge import load_knowledge
from migration_knowledge.tools.recommend_bedrock import recommend_bedrock_model

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


class TestExactMatch:
    def test_gpt4o(self, knowledge):
        r = recommend_bedrock_model("gpt-4o", knowledge=knowledge)
        assert r["status"] == "ok"
        assert r["bedrock_name"] == "Claude Sonnet 4.6"
        assert r["source_pricing"]["input_per_1m"] == 2.50

    def test_gemini_flash(self, knowledge):
        r = recommend_bedrock_model("gemini-2.5-flash", knowledge=knowledge)
        assert r["bedrock_name"] == "Nova Lite"
        assert r["savings"]["cost_direction"] == "bedrock_cheaper"

    def test_claude_sonnet(self, knowledge):
        r = recommend_bedrock_model("claude-3-5-sonnet", knowledge=knowledge)
        assert r["bedrock_name"] == "Claude Sonnet 4.6"
        assert r["savings"]["cost_direction"] == "comparable"

    def test_embedding(self, knowledge):
        r = recommend_bedrock_model("text-embedding-3-small", knowledge=knowledge)
        assert r["bedrock_name"] == "Titan Embeddings v2"
        assert any(w["type"] == "reindex_required" for w in r["warnings"])


class TestFuzzyMatch:
    def test_versioned_model(self, knowledge):
        r = recommend_bedrock_model("gpt-4o-2024-08-06", knowledge=knowledge)
        assert r["bedrock_name"] == "Claude Sonnet 4.6"

    def test_flash_thinking(self, knowledge):
        r = recommend_bedrock_model("gemini-2.5-flash-thinking", knowledge=knowledge)
        assert r["bedrock_name"] == "Nova Lite"

    def test_unknown_model(self, knowledge):
        r = recommend_bedrock_model("some-unknown-model-v3", knowledge=knowledge)
        assert r["bedrock_name"] == "Nova Pro"
        assert "No exact mapping" in r["rationale"]


class TestPreferenceOverrides:
    def test_quality_override(self, knowledge):
        r = recommend_bedrock_model("gemini-2.5-flash", ai_priority="quality", knowledge=knowledge)
        # Quality prefers Claude Sonnet/Opus
        assert "claude" in r["bedrock_model_id"].lower() or "sonnet" in r["bedrock_name"].lower() or "opus" in r["bedrock_name"].lower()
        assert r["override_applied"] == "quality"

    def test_latency_critical(self, knowledge):
        r = recommend_bedrock_model("gpt-4o", ai_latency="critical", knowledge=knowledge)
        # Latency critical prefers Haiku/Nova Lite/Micro
        assert r["override_applied"] == "latency_critical"


class TestAssessment:
    def test_strong_migrate(self, knowledge):
        r = recommend_bedrock_model("gpt-4-turbo", knowledge=knowledge)
        assert r["assessment"] == "strong_migrate"
        assert r["savings"]["blended_savings_pct"] > 25

    def test_source_cheaper(self, knowledge):
        r = recommend_bedrock_model("gpt-4.1", knowledge=knowledge)
        assert r["savings"]["cost_direction"] == "source_cheaper"

    def test_recommend_stay_with_cost_priority(self, knowledge):
        r = recommend_bedrock_model("gpt-4.1", ai_priority="cost", knowledge=knowledge)
        assert r["assessment"] in ("weak_migrate", "recommend_stay")


class TestVolumeWarnings:
    def test_high_volume_quota_warning(self, knowledge):
        r = recommend_bedrock_model("gpt-4o", ai_token_volume="high", knowledge=knowledge)
        assert any(w["type"] == "quota_risk" for w in r["warnings"])

    def test_high_volume_tiered_strategy(self, knowledge):
        r = recommend_bedrock_model("gpt-4o", ai_token_volume="high", knowledge=knowledge)
        assert r["tiered_strategy"] is not None
        assert r["tiered_strategy"]["recommended"] is True

    def test_low_volume_no_warnings(self, knowledge):
        r = recommend_bedrock_model("gpt-4o", ai_token_volume="low", knowledge=knowledge)
        assert not any(w["type"] == "quota_risk" for w in r["warnings"])
        assert r["tiered_strategy"] is None


class TestLegacyModels:
    def test_legacy_warning(self, knowledge):
        r = recommend_bedrock_model("gpt-4", knowledge=knowledge)
        assert any(w["type"] == "legacy_source" for w in r["warnings"])


class TestCapabilityGaps:
    def test_audio_gap_triggers_recommend_stay(self, knowledge):
        r = recommend_bedrock_model("gpt-5.5", capabilities_used=["text_generation", "audio"], knowledge=knowledge)
        assert r["assessment"] == "recommend_stay"
        assert len(r["capability_gaps"]) == 1
        assert r["capability_gaps"][0]["capability"] == "audio"

    def test_no_gap_when_capabilities_match(self, knowledge):
        r = recommend_bedrock_model("gpt-5.5", capabilities_used=["text_generation", "vision"], knowledge=knowledge)
        assert r["capability_gaps"] == []
        assert r["assessment"] != "recommend_stay"

    def test_no_gap_without_capabilities_provided(self, knowledge):
        r = recommend_bedrock_model("gpt-5.5", knowledge=knowledge)
        assert r["capability_gaps"] == []
        assert "capabilities_used_not_provided" in r["unresolved_factors"]

    def test_multiple_gaps(self, knowledge):
        r = recommend_bedrock_model("gpt-5.5", capabilities_used=["audio", "video", "realtime_api"], knowledge=knowledge)
        assert r["assessment"] == "recommend_stay"
        assert len(r["capability_gaps"]) == 3
