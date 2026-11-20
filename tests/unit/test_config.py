"""Unit tests for configuration and API key loading order."""

import os
from pathlib import Path
from fastapi.testclient import TestClient

from app.config import (
    FALLBACK_MODEL_DEFAULT,
    PRIMARY_MODEL_DEFAULT,
    get_fallback_model,
    get_model,
    is_ai_configured,
    load_api_key,
)
from app.main import app


def test_env_var_beats_file(tmp_path: Path, monkeypatch) -> None:
    """Verify GEMINI_API_KEY environment variable takes precedence over files."""
    dummy_file = tmp_path / "env_file_key.txt"
    dummy_file.write_text("file-key-value\n", encoding="utf-8")
    repo_file = tmp_path / "gemini_api_key.txt"
    repo_file.write_text("repo-key-value\n", encoding="utf-8")

    monkeypatch.setenv("GEMINI_API_KEY", "  env-key-value  ")
    monkeypatch.setenv("GEMINI_API_KEY_FILE", str(dummy_file))

    assert load_api_key(repo_root=tmp_path) == "env-key-value"


def test_file_env_var_beats_repo_root(tmp_path: Path, monkeypatch) -> None:
    """Verify GEMINI_API_KEY_FILE takes precedence over repo root file."""
    dummy_file = tmp_path / "custom_key.txt"
    dummy_file.write_text("custom-file-key\n", encoding="utf-8")
    repo_file = tmp_path / "gemini_api_key.txt"
    repo_file.write_text("repo-key-value\n", encoding="utf-8")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY_FILE", str(dummy_file))

    assert load_api_key(repo_root=tmp_path) == "custom-file-key"


def test_repo_root_fallback(tmp_path: Path, monkeypatch) -> None:
    """Verify fallback to gemini_api_key.txt in repo root when env vars are absent."""
    repo_file = tmp_path / "gemini_api_key.txt"
    repo_file.write_text("root-key-content\n", encoding="utf-8")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_FILE", raising=False)

    assert load_api_key(repo_root=tmp_path) == "root-key-content"


def test_missing_key_behavior(tmp_path: Path, monkeypatch) -> None:
    """Verify missing key returns None and does not crash application."""
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_FILE", raising=False)

    assert load_api_key(repo_root=empty_dir) is None


def test_model_name_defaults_and_env(monkeypatch) -> None:
    """Verify default and overridden model names."""
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    assert get_model() == PRIMARY_MODEL_DEFAULT
    assert get_fallback_model() == FALLBACK_MODEL_DEFAULT

    monkeypatch.setenv("GEMINI_MODEL", "custom-model")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "custom-fallback")
    assert get_model() == "custom-model"
    assert get_fallback_model() == "custom-fallback"


def test_health_endpoint() -> None:
    """Verify GET /health returns 200 with status, ai_configured, and model."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["ai_configured"], bool)
    assert data["model"] == get_model()
    assert data["fallback_model"] == get_fallback_model()
