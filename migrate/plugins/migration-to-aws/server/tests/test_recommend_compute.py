"""Unit tests for recommend_compute_target.

Each test case maps to a scenario from compute.md or a boundary condition.
"""

from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.recommend_compute import recommend_compute_target

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


# --- Cloud Run (container) scenarios ---

def test_cloud_run_basic_fargate(knowledge):
    """Cloud Run stateless API → Fargate, snapped sizing."""
    result = recommend_compute_target(
        service_type="container", timeout_seconds=60, vcpu=1, memory_gb=0.5,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"
    assert result["aws_config"]["cpu"] == 1
    assert result["aws_config"]["memory_gb"] >= 2  # snapped up to Fargate min for 1 vCPU


def test_cloud_run_gpu_excluded_to_ec2(knowledge):
    """Cloud Run with GPU → Fargate excluded → EC2."""
    result = recommend_compute_target(
        service_type="container", vcpu=4, memory_gb=16, gpu=True,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"
    assert "instance_type" in result["aws_config"]


def test_cloud_run_high_vcpu_to_ec2(knowledge):
    """Cloud Run >16 vCPU → Fargate excluded → EC2."""
    result = recommend_compute_target(
        service_type="container", vcpu=32, memory_gb=64, gpu=False,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"


def test_cloud_run_high_memory_to_ec2(knowledge):
    """Cloud Run >120 GB memory → Fargate excluded → EC2."""
    result = recommend_compute_target(
        service_type="container", vcpu=8, memory_gb=200, gpu=False,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"


# --- Cloud Functions (function) scenarios ---

def test_cloud_functions_short_lambda(knowledge):
    """Cloud Functions <15min → Lambda."""
    result = recommend_compute_target(
        service_type="function", timeout_seconds=540, vcpu=0.25, memory_gb=0.5,
        workload_pattern="event-driven", knowledge=knowledge,
    )
    assert result["aws_service"] == "Lambda"
    assert result["aws_config"]["memory_mb"] == 512
    assert result["aws_config"]["timeout_seconds"] == 540


def test_cloud_functions_long_timeout_fargate(knowledge):
    """Cloud Functions >15min → Lambda excluded → Fargate."""
    result = recommend_compute_target(
        service_type="function", timeout_seconds=1200, vcpu=0.5, memory_gb=1,
        workload_pattern="event-driven", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"
    assert "cpu" in result["aws_config"]


def test_cloud_functions_python27_fargate(knowledge):
    """Cloud Functions Python 2.7 → Lambda excluded → Fargate."""
    result = recommend_compute_target(
        service_type="function", timeout_seconds=60, vcpu=0.25, memory_gb=0.5,
        runtime="python27", workload_pattern="event-driven", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"


# --- Compute Engine (vm) scenarios ---

def test_compute_engine_basic_ec2(knowledge):
    """Compute Engine basic → EC2."""
    result = recommend_compute_target(
        service_type="vm", vcpu=2, memory_gb=4,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"
    assert result["aws_config"]["instance_type"] == "t3.medium"


def test_compute_engine_windows_forces_ec2(knowledge):
    """Windows workload → always EC2 regardless of other signals."""
    result = recommend_compute_target(
        service_type="vm", vcpu=2, memory_gb=8,
        workload_pattern="windows-only", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"


def test_compute_engine_cost_sensitive_alternative(knowledge):
    """EC2 with high cost sensitivity → EC2 primary, Fargate as alternative."""
    result = recommend_compute_target(
        service_type="vm", vcpu=2, memory_gb=4,
        workload_pattern="always-on", cost_sensitivity="high", knowledge=knowledge,
    )
    assert result["aws_service"] == "EC2"
    assert len(result["alternatives"]) > 0
    assert result["alternatives"][0]["aws_service"] == "Fargate"
    assert result["tie_break_required"] is True


# --- GKE (kubernetes) scenarios ---

def test_gke_eks_managed(knowledge):
    """GKE + kubernetes_pref=eks-managed → EKS."""
    result = recommend_compute_target(
        service_type="container", vcpu=4, memory_gb=16,
        kubernetes_pref="eks-managed", knowledge=knowledge,
    )
    assert result["aws_service"] == "EKS"


def test_gke_no_preference_fargate(knowledge):
    """GKE + no kubernetes preference → Fargate (not EKS)."""
    result = recommend_compute_target(
        service_type="container", vcpu=2, memory_gb=4,
        kubernetes_pref=None, knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"


def test_gke_ecs_fargate_preference(knowledge):
    """GKE + kubernetes_pref=ecs-fargate → Fargate."""
    result = recommend_compute_target(
        service_type="container", vcpu=2, memory_gb=4,
        kubernetes_pref="ecs-fargate", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"


# --- Workload pattern adjustments ---

def test_always_on_function_switches_to_fargate(knowledge):
    """Function type but always-on → Lambda switched to Fargate."""
    result = recommend_compute_target(
        service_type="function", timeout_seconds=60, vcpu=0.5, memory_gb=1,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"


# --- App Runner forbidden ---

def test_app_runner_never_recommended(knowledge):
    """No input combination should produce App Runner."""
    result = recommend_compute_target(
        service_type="container", vcpu=1, memory_gb=2,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] != "App Runner"


# --- Fargate sizing validation ---

def test_fargate_sizing_snaps_up(knowledge):
    """0.25 vCPU / 0.5 GB → snapped to valid combo (0.25 / 0.5)."""
    result = recommend_compute_target(
        service_type="container", vcpu=0.25, memory_gb=0.5,
        workload_pattern="event-driven", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"
    assert result["aws_config"]["cpu"] == 0.25
    assert result["aws_config"]["memory_gb"] == 0.5


def test_fargate_sizing_3vcpu_snaps_to_4(knowledge):
    """3 vCPU → snapped up to 4 vCPU tier."""
    result = recommend_compute_target(
        service_type="container", vcpu=3, memory_gb=8,
        workload_pattern="always-on", knowledge=knowledge,
    )
    assert result["aws_service"] == "Fargate"
    assert result["aws_config"]["cpu"] == 4
    assert result["aws_config"]["memory_gb"] == 8
