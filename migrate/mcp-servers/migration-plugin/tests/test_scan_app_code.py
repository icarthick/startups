"""Tests for scan_app_code tool."""

from pathlib import Path

import pytest

from migration_orchestrator.knowledge import load_knowledge
from migration_orchestrator.tools.scan_app_code import scan_app_code

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


@pytest.fixture
def python_gcp_project(tmp_path):
    """Project with GCP SDK imports."""
    (tmp_path / "app.py").write_text(
        "from google.cloud import storage\nfrom google.cloud import pubsub_v1\n"
    )
    (tmp_path / "requirements.txt").write_text("google-cloud-storage\ngoogle-cloud-pubsub\n")
    return tmp_path


@pytest.fixture
def ai_project(tmp_path):
    """Project with AI/ML imports."""
    (tmp_path / "model.py").write_text(
        "from google.cloud import aiplatform\nimport openai\nclient = openai.OpenAI()\n"
    )
    (tmp_path / "requirements.txt").write_text("google-cloud-aiplatform\nopenai\n")
    return tmp_path


@pytest.fixture
def agentic_project(tmp_path):
    """Project with agentic framework."""
    (tmp_path / "agent.py").write_text(
        "from langgraph.graph import StateGraph\ngraph = StateGraph()\ngraph.add_node('a', fn)\n"
    )
    (tmp_path / "requirements.txt").write_text("langgraph\nopenai\n")
    return tmp_path


class TestNoSourceFiles:
    def test_empty_dir(self, tmp_path, knowledge):
        result = scan_app_code(str(tmp_path), knowledge)
        assert result["status"] == "skipped"

    def test_only_non_source_files(self, tmp_path, knowledge):
        (tmp_path / "README.md").write_text("# Hello")
        (tmp_path / "data.csv").write_text("a,b\n1,2\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert result["status"] == "skipped"


class TestSecretExclusion:
    def test_excludes_env_files(self, tmp_path, knowledge):
        (tmp_path / "app.py").write_text("from google.cloud import storage\n")
        (tmp_path / ".env").write_text("SECRET_KEY=abc123\n")
        (tmp_path / ".env.production").write_text("DB_PASS=secret\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert ".env" in result["secret_files_excluded"]
        assert ".env.production" in result["secret_files_excluded"]

    def test_excludes_credential_files(self, tmp_path, knowledge):
        (tmp_path / "app.py").write_text("print('hi')\n")
        (tmp_path / "credentials.json").write_text("{}")
        (tmp_path / "my-service-account.json").write_text("{}")
        result = scan_app_code(str(tmp_path), knowledge)
        assert "credentials.json" in result["secret_files_excluded"]
        assert "my-service-account.json" in result["secret_files_excluded"]


class TestAuthExclusion:
    def test_detects_auth0(self, tmp_path, knowledge):
        (tmp_path / "auth.py").write_text("from auth0.authentication import Database\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert len(result["auth_exclusions"]) == 1
        assert result["auth_exclusions"][0]["provider"] == "Auth0"

    def test_detects_nextauth(self, tmp_path, knowledge):
        (tmp_path / "auth.ts").write_text("import NextAuth from 'next-auth'\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert result["auth_exclusions"][0]["provider"] == "NextAuth"


class TestGCPImports:
    def test_detects_python_imports(self, python_gcp_project, knowledge):
        result = scan_app_code(str(python_gcp_project), knowledge)
        services = {i["service"] for i in result["gcp_imports"]}
        assert "Cloud Storage" in services
        assert "Pub/Sub" in services

    def test_detects_js_imports(self, tmp_path, knowledge):
        (tmp_path / "index.ts").write_text(
            "import { Storage } from '@google-cloud/storage'\n"
            "import { Firestore } from '@google-cloud/firestore'\n"
        )
        result = scan_app_code(str(tmp_path), knowledge)
        services = {i["service"] for i in result["gcp_imports"]}
        assert "Cloud Storage" in services
        assert "Firestore" in services

    def test_deduplicates_by_service(self, tmp_path, knowledge):
        (tmp_path / "a.py").write_text("from google.cloud import storage\n")
        (tmp_path / "b.py").write_text("from google.cloud import storage\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert len(result["gcp_imports"]) == 1


class TestAISignals:
    def test_detects_vertex_ai(self, ai_project, knowledge):
        result = scan_app_code(str(ai_project), knowledge)
        signal_ids = {s["id"] for s in result["ai_signals"]}
        assert "vertex_ai" in signal_ids
        assert "openai" in signal_ids

    def test_confidence_high_with_multiple_strong(self, ai_project, knowledge):
        result = scan_app_code(str(ai_project), knowledge)
        assert result["ai_confidence"] >= 0.95
        assert result["ai_gate_passed"] is True

    def test_no_ai_signals(self, python_gcp_project, knowledge):
        result = scan_app_code(str(python_gcp_project), knowledge)
        assert result["ai_confidence"] == 0.0
        assert result["ai_gate_passed"] is False

    def test_detects_from_manifest(self, tmp_path, knowledge):
        (tmp_path / "app.py").write_text("print('hello')\n")
        (tmp_path / "requirements.txt").write_text("openai==1.0\nflask\n")
        result = scan_app_code(str(tmp_path), knowledge)
        signal_ids = {s["id"] for s in result["ai_signals"]}
        assert "openai" in signal_ids


class TestAgenticSignals:
    def test_detects_langgraph(self, agentic_project, knowledge):
        result = scan_app_code(str(agentic_project), knowledge)
        assert result["agentic_classification"]["is_agentic"] is True
        assert result["agentic_classification"]["framework"] == "langgraph"

    def test_not_agentic_without_framework(self, python_gcp_project, knowledge):
        result = scan_app_code(str(python_gcp_project), knowledge)
        assert result["agentic_classification"]["is_agentic"] is False

    def test_detects_crewai(self, tmp_path, knowledge):
        (tmp_path / "crew.py").write_text("from crewai import Crew, Agent\ncrew = Crew()\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert result["agentic_classification"]["is_agentic"] is True
        assert result["agentic_classification"]["framework"] == "crewai"


class TestWebSocketSignals:
    def test_detects_websocket(self, tmp_path, knowledge):
        (tmp_path / "ws.py").write_text("from fastapi import WebSocket\nasync def ws_endpoint(ws: WebSocket):\n    pass\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert len(result["websocket_signals"]) > 0

    def test_no_websocket(self, python_gcp_project, knowledge):
        result = scan_app_code(str(python_gcp_project), knowledge)
        assert result["websocket_signals"] == []


class TestGatewaySignals:
    def test_detects_litellm(self, tmp_path, knowledge):
        (tmp_path / "llm.py").write_text("from litellm import completion\nresult = completion(model='gpt-4')\n")
        result = scan_app_code(str(tmp_path), knowledge)
        assert len(result["gateway_signals"]) > 0
        assert result["gateway_signals"][0]["gateway_type"] == "llm_router"

    def test_detects_openrouter_env(self, tmp_path, knowledge):
        (tmp_path / "app.py").write_text("import os\n")
        (tmp_path / ".env.example").write_text("OPENROUTER_API_KEY=xxx\n")
        # .env.example not in exclusion list, so it gets scanned as a source? No — it's not .py
        # Need to put it somewhere scannable
        (tmp_path / "config.py").write_text("OPENROUTER_API_KEY = os.environ['OPENROUTER_API_KEY']\n")
        result = scan_app_code(str(tmp_path), knowledge)
        gw_ids = {g["id"] for g in result["gateway_signals"]}
        assert "openrouter" in gw_ids
