"""API contract tests — the safety net for prompt tuning (9.1): any change to
endpoints, SSE framing, or the capture mailbox that breaks the panel shows here."""

import time

import pytest

from paper_agent.api import server


# ── health ──────────────────────────────────────────────────────────────────

def test_health_versioned(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]  # versioned so stale daemons are identifiable
    assert isinstance(body["pid"], int)
    assert body["api_key_present"] is False


def test_health_reports_api_key(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert client.get("/api/health").json()["api_key_present"] is True


# ── capture mailbox (§4.2) ──────────────────────────────────────────────────

def _post_capture(client, text="hello"):
    res = client.post("/api/capture", json={
        "selected_text": text, "source_app": "Safari",
        "source_title": "t", "source_url": "https://arxiv.org/abs/1706.03762",
    })
    assert res.status_code == 200
    return res.json()


def test_capture_roundtrip(client):
    body = _post_capture(client)
    assert body["id"] and body["expires_at"] > time.time()

    got = client.get(f"/api/capture/{body['id']}")
    assert got.status_code == 200
    payload = got.json()
    assert payload["selected_text"] == "hello"
    assert payload["age"] >= 0


def test_capture_expires(client):
    capture_id = _post_capture(client)["id"]
    # Expire it by backdating the stored timestamp (no time patching needed).
    ts, payload = server._CAPTURES[capture_id]
    server._CAPTURES[capture_id] = (ts - server._CAPTURE_TTL - 1, payload)
    assert client.get(f"/api/capture/{capture_id}").status_code == 404


def test_capture_unknown_id_404(client):
    assert client.get("/api/capture/nope").status_code == 404


def test_capture_cap_and_fifo_eviction(client):
    ids = [_post_capture(client, f"t{i}")["id"] for i in range(server._CAPTURE_CAP + 5)]
    assert len(server._CAPTURES) == server._CAPTURE_CAP
    # Oldest entries evicted first (insertion order).
    assert client.get(f"/api/capture/{ids[0]}").status_code == 404
    assert client.get(f"/api/capture/{ids[-1]}").status_code == 200


# ── resolve ─────────────────────────────────────────────────────────────────

def test_resolve_no_input(client):
    res = client.post("/api/resolve", json={"source_url": "", "selected_text": ""})
    assert res.status_code == 200
    body = res.json()
    assert body["found"] is False
    assert body["thread_state"] in ("fresh", "new_paper", "no_paper")


# ── ask SSE contract (mocked LLM — no network) ──────────────────────────────

@pytest.fixture()
def mock_ask(monkeypatch):
    async def fake_ask(**kwargs):
        yield "tok-1"
        yield "tok-2"

    monkeypatch.setattr(server, "run_ask", fake_ask)
    monkeypatch.setattr("paper_agent.context.get_last_session_file",
                        lambda: "sessions/reading-x.md")


def test_ask_sse_framing(client, monkeypatch, mock_ask):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with client.stream("POST", "/api/spaces/test-space/ask",
                       json={"question": "q"}) as res:
        assert res.status_code == 200
        events = [line[len("data: "):] for line in res.iter_lines()
                  if line.startswith("data: ")]
    assert events[0] == "tok-1"  # raw tokens stream as data lines
    assert events[-2] == "[DONE]"  # sentinel before the save confirmation
    assert events[-1].startswith('{"session_path"')


def test_ask_missing_key_503(client):
    res = client.post("/api/spaces/test-space/ask", json={"question": "q"})
    assert res.status_code == 503
    assert "OPENROUTER_API_KEY" in res.json()["detail"]


def test_ask_unknown_space_404(client, monkeypatch, mock_ask):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    res = client.post("/api/spaces/does-not-exist/ask", json={"question": "q"})
    assert res.status_code == 404


# ── secret-gated destructive routes ─────────────────────────────────────────

def test_delete_requires_secret(client, monkeypatch):
    monkeypatch.setenv("PAPER_AGENT_SECRET", "test-secret")
    res = client.delete("/api/spaces/test-space")
    assert res.status_code == 403
    res = client.delete("/api/spaces/test-space", headers={"X-Paper-Agent-Secret": "wrong"})
    assert res.status_code == 403


# ── static /app serving (the page the panel loads) ──────────────────────────

def test_app_index_served(client):
    res = client.get("/app")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert 'id="app"' in res.text or "composer" in res.text


def test_app_assets_served(client):
    for asset in ("app.js", "styles.css", "sse.js", "marked.min.js"):
        assert client.get(f"/app/{asset}").status_code == 200
