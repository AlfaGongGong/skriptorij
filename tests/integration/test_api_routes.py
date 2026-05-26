

"""Integration testovi za API rute."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from flask import Flask
from app import create_app
from config.ai_config import MODEL_MAP


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_loads(client):
    # First visit redirects to /intro (302)
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/intro" in resp.headers["Location"]

    # After intro_seen cookie is set, / returns 200 with index.html
    client.set_cookie("intro_seen", "true")
    resp = client.get("/")
    assert resp.status_code == 200


def test_intro_loads(client):
    resp = client.get("/intro")
    assert resp.status_code == 200
    assert b"intro-overlay" in resp.data


def test_status_endpoint(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "status" in data


def test_books_endpoint(client):
    resp = client.get("/api/books")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "books" in data


def test_models_endpoint(client):
    resp = client.get("/api/dev_models")
    assert resp.status_code == 200
    models = resp.get_json()
    assert isinstance(models, list)
    assert "V8_TURBO" in models


def test_fleet_endpoint(client):
    resp = client.get("/api/fleet")
    # Returns 200 with data or 500 with error if no dev_api.json
    assert resp.status_code in (200, 500)


def test_keys_endpoint(client):
    resp = client.get("/api/keys")
    # Returns 200 with empty dict if no dev_api.json
    assert resp.status_code == 200


def test_control_pause(client):
    resp = client.post("/control/pause")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["action"] == "pause"


def test_control_resume(client):
    resp = client.post("/control/resume")
    assert resp.status_code == 200


def test_control_unknown_action(client):
    resp = client.post("/control/invalid_action")
    assert resp.status_code == 400


def test_export_without_output(client):
    resp = client.get("/api/export/json")
    assert resp.status_code == 404


def test_start_missing_book(client):
    resp = client.post(
        "/api/start",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_ping_key_uses_gemini_native_payload(client, tmp_path, monkeypatch):
    import api.routes.keys as keys_routes

    cfg = tmp_path / "dev_api.json"
    cfg.write_text(json.dumps({"GEMINI": ["gem_test_key"]}), "utf-8")
    monkeypatch.setattr(keys_routes, "CONFIG_PATH", str(cfg))
    app = Flask(__name__)
    app.register_blueprint(keys_routes.bp)

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(keys_routes.requests, "post", fake_post)

    with app.test_client() as local_client:
        resp = local_client.post("/api/keys/GEMINI/0/ping")

    assert resp.status_code == 200
    assert "/v1beta/models/" in captured["url"]
    assert "?key=gem_test_key" in captured["url"]
    assert "Authorization" not in captured["headers"]
    assert "contents" in captured["json"]
    assert "messages" not in captured["json"]


def test_ping_key_uses_gemma_native_payload(client, tmp_path, monkeypatch):
    import api.routes.keys as keys_routes

    cfg = tmp_path / "dev_api.json"
    cfg.write_text(json.dumps({"GEMMA": ["gemma_test_key"]}), "utf-8")
    monkeypatch.setattr(keys_routes, "CONFIG_PATH", str(cfg))
    app = Flask(__name__)
    app.register_blueprint(keys_routes.bp)

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(keys_routes.requests, "post", fake_post)

    with app.test_client() as local_client:
        resp = local_client.post("/api/keys/GEMMA/0/ping")

    default_gemma_model = MODEL_MAP["GEMMA"]
    assert resp.status_code == 200
    assert f"/v1beta/models/{default_gemma_model}:generateContent" in captured["url"]
    assert "?key=gemma_test_key" in captured["url"]
    assert "Authorization" not in captured["headers"]
    assert "contents" in captured["json"]
    assert "messages" not in captured["json"]
