import zipfile
from pathlib import Path

import pytest

from core import odluke, zavrsi


@pytest.fixture(autouse=True)
def izolacija(tmp_path, monkeypatch):
    monkeypatch.setattr(odluke, "PUTANJA", tmp_path / "odluke.jsonl")
    monkeypatch.setattr(zavrsi, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(zavrsi, "STATUS_FILE", tmp_path / "logs" / "st.json")


def _ck(tmp_path, tekst="<!-- chunk_sha:v2:x -->\n<p>Ona prelazi igralište za kriket i ide.</p>"):
    ck = tmp_path / "ck"
    ck.mkdir()
    (ck / "part0004.html_blok_0.chk").write_text(tekst, "utf-8")
    return ck


def test_za_primjenu_zadnja_odluka_i_novo():
    odluke.zabiljezi("K", "part1.html_blok_0", "en a", "hr a", "negacija", "prevedi_ponovo", "novo a")
    odluke.zabiljezi("K", "part1.html_blok_1", "en b", "hr b", "broj", "ostavi")
    odluke.zabiljezi("K", "part1.html_blok_2", "en c", "hr c", "ime", "prevedi_ponovo", "")
    odluke.zabiljezi("K", "part1.html_blok_3", "en d", "hr d", "ime", "prevedi_ponovo", "novo d")
    odluke.zabiljezi("K", "part1.html_blok_3", "en d", "hr d", "ime", "ponisti")
    odluke.zabiljezi("X", "part9.html_blok_0", "en e", "hr e", "ime", "prevedi_ponovo", "novo e")
    assert [z["hr"] for z in odluke.za_primjenu("K")] == ["hr a"]


def test_ispravke_parsiranje_bloka():
    odluke.zabiljezi("K", "part0004.html_blok_2", "e", "hr1", "broj", "prevedi_ponovo", "n1")
    odluke.zabiljezi("K", "CR!AB_split_011.html_blok_10.chk", "e", "hr2", "broj", "prevedi_ponovo", "n2")
    odluke.zabiljezi("K", "cudan_blok", "e", "hr3", "broj", "prevedi_ponovo", "n3")
    odluke.zabiljezi("K", "part1.html_blok_1", "e", "isto", "broj", "prevedi_ponovo", "isto")
    isp, pres = zavrsi.ispravke_iz_odluka("K")
    assert [(i["fajl"], i["blok"]) for i in isp] == [("part0004.html", 2), ("CR!AB_split_011.html", 10)]
    assert len(pres) == 2


def test_dry_ne_mijenja_fajl(tmp_path):
    ck = _ck(tmp_path)
    odluke.zabiljezi("K", "part0004.html_blok_0", "croquet", "prelazi igralište za kriket",
                     "broj", "prevedi_ponovo", "prelazi igralište za kroket")
    prije = (ck / "part0004.html_blok_0.chk").read_bytes()
    st = zavrsi.pokreni("K", None, ck, dry=True)
    assert st["stanje"] == "dry" and st["ispravke"] == {"ok": 1, "vec": 0, "fail": 0}
    assert (ck / "part0004.html_blok_0.chk").read_bytes() == prije


def test_primjena_backup_i_idempotentnost(tmp_path):
    ck = _ck(tmp_path)
    odluke.zabiljezi("K", "part0004.html_blok_0", "croquet", "prelazi igralište za kriket",
                     "broj", "prevedi_ponovo", "prelazi igralište za kroket")
    bdir = tmp_path / "bak"
    rez, isp, _ = zavrsi.primijeni_odluke("K", ck, bdir, False, lambda m: None)
    assert rez == {"ok": 1, "vec": 0, "fail": 0}
    t = (ck / "part0004.html_blok_0.chk").read_text("utf-8")
    assert "kroket" in t and "kriket" not in t and t.startswith("<!-- chunk_sha:v2:x -->")
    assert "kriket" in (bdir / "part0004.html_blok_0.chk").read_text("utf-8")
    rez2, _, _ = zavrsi.primijeni_odluke("K", ck, bdir, False, lambda m: None)
    assert rez2 == {"ok": 0, "vec": 1, "fail": 0}


def test_dvosmislen_fragment_ne_dira_fajl(tmp_path):
    ck = _ck(tmp_path, "<p>a prelazi igralište za kriket b</p><p>c prelazi igralište za kriket d</p>")
    odluke.zabiljezi("K", "part0004.html_blok_0", "e", "prelazi igralište za kriket",
                     "broj", "prevedi_ponovo", "prelazi igralište za kroket")
    prije = (ck / "part0004.html_blok_0.chk").read_bytes()
    rez, _, _ = zavrsi.primijeni_odluke("K", ck, None, False, lambda m: None)
    assert rez["fail"] == 1 and rez["ok"] == 0
    assert (ck / "part0004.html_blok_0.chk").read_bytes() == prije


def test_provjera_u_epubu(tmp_path):
    ep = tmp_path / "t.epub"
    with zipfile.ZipFile(ep, "w") as z:
        z.writestr("OEBPS/ch1.xhtml", "<html><body><p>Ona je <i>prelazila</i> igralište za kriket.</p></body></html>")
    isp = [{"id": "a", "novo": "prelazila igralište za kriket"}, {"id": "b", "novo": "nema ga nigdje"}]
    r = zavrsi.provjeri_u_epubu(ep, isp)
    assert r == {"novo_u_epubu": 1, "nije_nadjeno": ["b"]}


def _app(monkeypatch, tmp_path, clean="K", izvor=None):
    flask = pytest.importorskip("flask")
    try:
        from api.routes import processing as P
    except Exception as e:
        pytest.skip(f"processing.py se ne moze uvesti u testu: {e!r}")
    root = tmp_path / "ckroot"
    ck = root / f"_skr_{clean}" / "checkpoints"
    ck.mkdir(parents=True)
    monkeypatch.setattr(P, "CHECKPOINT_BASE_DIR", root)
    monkeypatch.setattr(P, "_p26_knjiga", lambda: clean)
    monkeypatch.setattr(P, "_p26_izvorni_epub", lambda: izvor)
    app = flask.Flask("t")
    app.register_blueprint(P.bp)
    return app, ck


def test_ruta_dry_i_status(monkeypatch, tmp_path):
    app, ck = _app(monkeypatch, tmp_path)
    (ck / "part0004.html_blok_0.chk").write_text("<p>prelazi igralište za kriket</p>", "utf-8")
    odluke.zabiljezi("K", "part0004.html_blok_0", "e", "prelazi igralište za kriket",
                     "broj", "prevedi_ponovo", "prelazi igralište za kroket")
    c = app.test_client()
    r = c.post("/api/review/zavrsi", json={"dry": True})
    assert r.status_code == 200
    j = r.get_json()
    assert j["stanje"] == "dry" and j["ispravke"]["ok"] == 1
    assert "kriket" in (ck / "part0004.html_blok_0.chk").read_text("utf-8")
    s = c.get("/api/review/zavrsi/status")
    assert s.status_code == 200 and "stanje" in s.get_json()


def test_ruta_bez_izvora_i_bez_knjige(monkeypatch, tmp_path):
    app, ck = _app(monkeypatch, tmp_path)
    r = app.test_client().post("/api/review/zavrsi", json={})
    assert r.status_code == 404 and "error" in r.get_json()
    from api.routes import processing as P
    monkeypatch.setattr(P, "_p26_knjiga", lambda: "")
    r2 = app.test_client().post("/api/review/zavrsi", json={"dry": True})
    assert r2.status_code == 404
