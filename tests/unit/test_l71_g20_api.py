"""L71/G20 DIO 3: API vraca 422 + poruku korisniku kad stilizator odbije (G20)."""
import pytest


@pytest.fixture()
def klijent(tmp_path, monkeypatch):
    import app as A
    import config.settings as cfg
    import epub.manager as M
    izlaz = tmp_path / "izlaz"
    izlaz.mkdir()
    (izlaz / "k.epub").write_bytes(b"PK")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", izlaz)
    monkeypatch.setattr(cfg, "INPUT_DIR", izlaz)
    fa = A.create_app()
    fa.config["TESTING"] = True
    return fa.test_client(), M, monkeypatch


def test_g20_je_422_s_porukom(klijent):
    c, M, mp = klijent
    mp.setattr(M.EpubStylerManager, "stilizuj",
               lambda self, options=None: {"ok": False, "error": "G20: knjiga je ostala engleska (x)"})
    r = c.post("/api/style_epub", json={"file": "k.epub"})
    d = r.get_json()
    assert r.status_code == 422 and d["g20"] is True and "Dovrsi prijevod" in d["poruka_korisniku"]


def test_druga_greska_ostaje_500(klijent):
    c, M, mp = klijent
    mp.setattr(M.EpubStylerManager, "stilizuj",
               lambda self, options=None: {"ok": False, "error": "nesto drugo"})
    r = c.post("/api/style_epub", json={"file": "k.epub"})
    assert r.status_code == 500 and "g20" not in r.get_json()
