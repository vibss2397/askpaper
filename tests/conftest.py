"""Shared fixtures: an isolated vault (via PAPER_AGENT_VAULT) + a TestClient.

The real ~/.paper-vault is never touched, and the repo's real .env is kept out
of the tests (no live API keys, no real secret). LLM entry points are
monkeypatched per-test (no network)."""

import pytest
import yaml
from fastapi.testclient import TestClient

from paper_agent.api import server
from paper_agent import vault


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Disable .env discovery and strip real credentials for determinism."""
    monkeypatch.setattr("paper_agent.config._load_env", lambda: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PAPER_AGENT_SECRET", raising=False)


@pytest.fixture()
def tmp_vault(tmp_path, monkeypatch):
    """Point the app at a throwaway vault with one initialized space."""
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("PAPER_AGENT_VAULT", str(vault_path))
    vault.init_vault_and_space("test-space")
    cfg_dir = vault_path / ".paper-agent"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text(yaml.dump({
        "vault_path": str(vault_path),
        "model": "test/model",
    }))
    return vault_path


@pytest.fixture()
def client(tmp_vault):
    with TestClient(server.app) as c:
        yield c
