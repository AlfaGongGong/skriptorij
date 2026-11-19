import pytest


@pytest.fixture()
def klijent(tmp_path, monkeypatch):
    import app as A
    ulaz = tmp_path / "MoonReader" / "booklyfi"
    stil = tmp_path / "MoonReader" / "STYLED"
    izlaz = tmp_path / "izlaz"
    for d in (ulaz, stil, izlaz):
        d.mkdir(parents=True)
    monkeypatch.setattr(A, "INPUT_DIR", ulaz)
    monkeypatch.setattr(A, "OUTPUT_DIR", izlaz)
    # nova instanca: zahtjevi na zajednicki A.app bi kasnije srusili `import main`
    # (Flask: rute se ne mogu dodavati nakon prvog zahtjeva)
    flask_app = A.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client(), stil, ulaz, izlaz


def test_preuzimanje_iz_styled(klijent):
    c, stil, _, _ = klijent
    (stil / "Knjiga_STYLED.epub").write_bytes(b"PK-test")
    r = c.get("/api/download/Knjiga_STYLED.epub")
    assert r.status_code == 200 and r.data == b"PK-test"
    r.close()


def test_preuzimanje_iz_izlaza(klijent):
    c, _, _, izlaz = klijent
    (izlaz / "A_PREVEDENO.epub").write_bytes(b"PK-a")
    r = c.get("/api/download/A_PREVEDENO.epub")
    assert r.status_code == 200 and r.data == b"PK-a"
    r.close()


def test_nepostojeci_je_404(klijent):
    c = klijent[0]
    assert c.get("/api/download/nema.epub").status_code == 404


def test_ne_epub_je_400(klijent):
    c, stil, _, _ = klijent
    (stil / "x.txt").write_text("x")
    assert c.get("/api/download/x.txt").status_code == 400


def test_prolaz_kroz_mape_odbijen(klijent):
    c, stil, _, _ = klijent
    (stil.parent / "tajna.epub").write_bytes(b"tajna")
    r = c.get("/api/download/..%2Ftajna.epub")
    assert r.status_code != 200 and b"tajna" not in r.data
    r.close()
