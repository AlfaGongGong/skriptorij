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


def test_qa_flags_i_human_review_zivi(client):
    for u in ("/api/qa_flags", "/api/human_review"):
        r = client.get(u)
        assert r.status_code == 200 and r.is_json, (u, r.status_code)


def test_quality_rute_registrirane(client):
    pravila = {(r.rule, m) for r in client.application.url_map.iter_rules() for m in r.methods}
    for u, m in (("/api/qa_flags", "GET"), ("/api/human_review", "GET"),
                 ("/api/quality_scores/send_to_fix", "POST"), ("/api/fix/marked_blocks", "POST"),
                 ("/api/quality_scores", "GET")):
        assert (u, m) in pravila, (u, m)


def test_nema_duplikata_pravila_i_metoda(client):
    vidjeno, dup = set(), []
    for r in client.application.url_map.iter_rules():
        for m in r.methods - {"HEAD", "OPTIONS"}:
            if (r.rule, m) in vidjeno:
                dup.append((r.rule, m))
            vidjeno.add((r.rule, m))
    assert not dup, dup
