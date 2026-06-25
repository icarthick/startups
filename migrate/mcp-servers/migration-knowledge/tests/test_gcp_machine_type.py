"""Unit tests for gcp_machine_type parser."""

import pytest

from migration_knowledge.tools.gcp_machine_type import parse_gcp_machine_type


# --- Standard pattern: family-class-vcpu ---

def test_n1_standard_4():
    result = parse_gcp_machine_type("n1-standard-4")
    assert result["vcpu"] == 4
    assert result["memory_gb"] == 15.0  # 4 × 3.75


def test_n1_highmem_16():
    """The exact case that failed in live run."""
    result = parse_gcp_machine_type("n1-highmem-16")
    assert result["vcpu"] == 16
    assert result["memory_gb"] == 104.0  # 16 × 6.5


def test_n1_highcpu_8():
    result = parse_gcp_machine_type("n1-highcpu-8")
    assert result["vcpu"] == 8
    assert result["memory_gb"] == pytest.approx(7.2)  # 8 × 0.9


def test_n2_standard_2():
    result = parse_gcp_machine_type("n2-standard-2")
    assert result["vcpu"] == 2
    assert result["memory_gb"] == 8.0  # 2 × 4


def test_n2_highmem_4():
    result = parse_gcp_machine_type("n2-highmem-4")
    assert result["vcpu"] == 4
    assert result["memory_gb"] == 32.0  # 4 × 8


def test_e2_standard_4():
    result = parse_gcp_machine_type("e2-standard-4")
    assert result["vcpu"] == 4
    assert result["memory_gb"] == 16.0  # 4 × 4


def test_c2_standard_16():
    result = parse_gcp_machine_type("c2-standard-16")
    assert result["vcpu"] == 16
    assert result["memory_gb"] == 64.0  # 16 × 4


# --- E2 presets ---

def test_e2_micro():
    result = parse_gcp_machine_type("e2-micro")
    assert result["vcpu"] == 0.25
    assert result["memory_gb"] == 1.0


def test_e2_small():
    result = parse_gcp_machine_type("e2-small")
    assert result["vcpu"] == 0.5
    assert result["memory_gb"] == 2.0


def test_e2_medium():
    result = parse_gcp_machine_type("e2-medium")
    assert result["vcpu"] == 2.0
    assert result["memory_gb"] == 4.0


# --- Custom types ---

def test_custom_4_8192():
    result = parse_gcp_machine_type("n1-custom-4-8192")
    assert result["vcpu"] == 4
    assert result["memory_gb"] == 8.0  # 8192 MB


def test_custom_e2():
    result = parse_gcp_machine_type("e2-custom-2-4096")
    assert result["vcpu"] == 2
    assert result["memory_gb"] == 4.0


# --- Edge cases ---

def test_unknown_family_fallback():
    """Unknown family but parseable → uses 4 GB/vCPU fallback."""
    result = parse_gcp_machine_type("x99-standard-8")
    assert result["vcpu"] == 8
    assert result["memory_gb"] == 32.0  # fallback: 8 × 4


def test_none_input():
    assert parse_gcp_machine_type(None) is None


def test_empty_string():
    assert parse_gcp_machine_type("") is None


def test_garbage():
    assert parse_gcp_machine_type("not-a-machine-type-at-all") is None
