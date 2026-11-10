"""P2.3: integracijski testovi ruta koje UI koristi (samo GET, bez pisanja; tolerantni na stanje diska)."""
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


def test_status_json(client):
    r = client.get("/api/status")
    assert r.status_code == 200 and "status" in r.get_json()


def test_books_json(client):
    r = client.get("/api/books")
    assert r.status_code == 200 and "books" in r.get_json()


def test_quality_scores_json(client):
    r = client.get("/api/quality_scores")
    assert r.status_code == 200 and r.is_json


def test_odluke_stat_json(client):
    r = client.get("/api/review/odluke/stat")
    assert r.status_code == 200 and isinstance(r.get_json(), dict)


def test_kartice_lista_ili_json_greska(client):
    r = client.get("/api/review/kartice")
    assert r.status_code in (200, 404) and r.is_json
    if r.status_code == 200:
        assert isinstance(r.get_json(), list)
    else:
        assert "error" in r.get_json()


def test_revizija_html(client):
    r = client.get("/revizija")
    assert r.status_code == 200 and "text/html" in r.content_type


def test_fleet(client):
    assert client.get("/api/fleet").status_code in (200, 500)


def test_p26_rute_registrirane(client):
    pravila = {r.rule for r in client.application.url_map.iter_rules()}
    for u in ("/revizija", "/api/review/kartice", "/api/review/odluka", "/api/review/prevedi",
              "/api/review/zavrsi", "/api/review/zavrsi/status", "/api/review/odluke/stat"):
        assert u in pravila, u
