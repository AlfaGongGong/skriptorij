import pytest


@pytest.fixture(scope="module")
def stvarna_app():
    try:
        import app as A
    except Exception as e:
        pytest.skip(f"app.py se ne moze uvesti u testu: {e!r}")
    return A.app


RUTE = [
    ("/revizija", "GET"), ("/api/review/kartice", "GET"), ("/api/review/odluka", "POST"),
    ("/api/review/odluke/stat", "GET"), ("/api/review/prevedi", "POST"),
    ("/api/review/zavrsi", "POST"), ("/api/review/zavrsi/status", "GET"),
]


@pytest.mark.parametrize("rule,metoda", RUTE)
def test_ruta_registrirana_na_stvarnom_appu(stvarna_app, rule, metoda):
    nadjeno = [r for r in stvarna_app.url_map.iter_rules() if r.rule == rule and metoda in r.methods]
    assert len(nadjeno) == 1, f"{metoda} {rule}: pravila={len(nadjeno)}"


def test_get_rute_nisu_404(stvarna_app):
    c = stvarna_app.test_client()
    for u in ("/revizija", "/api/review/zavrsi/status", "/api/review/odluke/stat"):
        assert c.get(u).status_code == 200, u
    r = c.get("/api/review/kartice")
    assert r.status_code in (200, 404) and r.is_json, "kartice moraju vratiti JSON (a ne HTML 404 rute)"


def test_nema_dupliranih_review_pravila(stvarna_app):
    from collections import Counter
    n = Counter((r.rule, tuple(sorted(r.methods - {"HEAD", "OPTIONS"}))) for r in stvarna_app.url_map.iter_rules()
                if r.rule.startswith(("/api/review", "/revizija")))
    dup = {k: v for k, v in n.items() if v > 1 and k[0] in {x[0] for x in RUTE}}
    assert not dup, dup
