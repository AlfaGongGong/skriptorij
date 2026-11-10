import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

from app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_names_rute_registrirane(client):
    pravila = {(r.rule, m) for r in client.application.url_map.iter_rules() for m in r.methods}
    assert ("/api/names/status", "GET") in pravila
    assert ("/api/names/replacement", "GET") in pravila
    assert ("/api/names/apply", "POST") in pravila


def test_names_get_nije_flask_404(client):
    for u in ("/api/names/status", "/api/names/replacement"):
        r = client.get(u)
        assert r.status_code != 404 or r.is_json, (u, r.status_code)


def test_nema_duplikata(client):
    vidjeno, dup = set(), []
    for r in client.application.url_map.iter_rules():
        for m in r.methods - {"HEAD", "OPTIONS"}:
            if (r.rule, m) in vidjeno:
                dup.append((r.rule, m))
            vidjeno.add((r.rule, m))
    assert not dup, dup
