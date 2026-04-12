"""Integration testovi za API rute."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200


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
