"""Unit tests for recommend_messaging_target."""

from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.recommend_messaging import recommend_messaging_target

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


def test_fanout_pattern_sns_sqs(knowledge):
    """Fan-out delivery pattern → SNS+SQS."""
    result = recommend_messaging_target(delivery_pattern="fan-out", knowledge=knowledge)
    assert result["aws_service"] == "SNS+SQS"
    assert result["aws_config"]["pattern"] == "SNS topic → SQS subscription(s)"


def test_point_to_point_sqs(knowledge):
    """Point-to-point delivery → SQS only."""
    result = recommend_messaging_target(delivery_pattern="point-to-point", knowledge=knowledge)
    assert result["aws_service"] == "SQS"
    assert result["aws_config"]["pattern"] == "SQS queue"


def test_multiple_subscribers_forces_sns(knowledge):
    """subscriber_count > 1 → SNS+SQS via constraint."""
    result = recommend_messaging_target(subscriber_count=3, knowledge=knowledge)
    assert result["aws_service"] == "SNS+SQS"


def test_single_subscriber_sqs(knowledge):
    """subscriber_count = 1 → SQS."""
    result = recommend_messaging_target(subscriber_count=1, knowledge=knowledge)
    assert result["aws_service"] == "SQS"


def test_ordering_required_fifo(knowledge):
    """Ordering required → FIFO queue."""
    result = recommend_messaging_target(
        delivery_pattern="point-to-point", ordering_required=True, knowledge=knowledge,
    )
    assert result["aws_service"] == "SQS"
    assert result["aws_config"]["fifo"] is True


def test_ordering_required_fanout_fifo(knowledge):
    """Fan-out + ordering → SNS+SQS FIFO."""
    result = recommend_messaging_target(
        delivery_pattern="fan-out", ordering_required=True, knowledge=knowledge,
    )
    assert result["aws_service"] == "SNS+SQS"
    assert result["aws_config"]["fifo"] is True


def test_ack_deadline_maps_to_visibility_timeout(knowledge):
    """ack_deadline_seconds → SQS visibility_timeout_seconds."""
    result = recommend_messaging_target(
        delivery_pattern="point-to-point", ack_deadline_seconds=60, knowledge=knowledge,
    )
    assert result["aws_config"]["visibility_timeout_seconds"] == 60


def test_default_visibility_timeout(knowledge):
    """No ack_deadline → default 30s visibility timeout."""
    result = recommend_messaging_target(delivery_pattern="point-to-point", knowledge=knowledge)
    assert result["aws_config"]["visibility_timeout_seconds"] == 30


def test_dlq_enabled_by_default(knowledge):
    """DLQ should be enabled by default."""
    result = recommend_messaging_target(delivery_pattern="point-to-point", knowledge=knowledge)
    assert result["aws_config"]["dlq"] is True


def test_no_inputs_defaults_sqs(knowledge):
    """No inputs → defaults to SQS."""
    result = recommend_messaging_target(knowledge=knowledge)
    assert result["aws_service"] == "SQS"


def test_result_structure(knowledge):
    """Verify output follows the standard recommend_* contract."""
    result = recommend_messaging_target(delivery_pattern="fan-out", knowledge=knowledge)
    assert "aws_service" in result
    assert "aws_config" in result
    assert "confidence" in result
    assert "rubric_applied" in result
    assert "alternatives" in result
    assert "tie_break_required" in result
    assert result["confidence"] == "inferred"
