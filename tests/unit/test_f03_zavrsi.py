"""F03 DIO a: popravci u core/zavrsi.py (R0-1, R9-22, R9-23, R9-24, R9-25, R9-26, R9-28)."""
import zipfile
from pathlib import Path

from core import odluke, zavrsi


def _wd(tmp_path, tekst, ime="a.html"):
    wd = tmp_path / "_skr_x"
    (wd / "checkpoints").mkdir(parents=True)
    f = wd / ime
    f.write_text("<html><body>" + tekst + "</body></html>", encoding="utf-8")
    return wd, f


def _isp(staro, novo):
    return [{"id": "t1", "fajl": "a.html", "blok": 0, "staro": staro, "novo": novo}]


def test_r0_1_atomic_write_text_uvezen_i_radi(tmp_path):
    assert callable(zavrsi.atomic_write_text)
    wd, f = _wd(tmp_path, "<p>Ona je rekla da ne ide.</p>")
    r = zavrsi.primijeni_u_html(wd / "checkpoints", _isp("Ona je rekla da ne ide", "Ona rece da ne ide"),
                                log=lambda m: None)
    assert r == {"ok": 1, "vec": 0, "fail": 0}
    assert "Ona rece da ne ide" in f.read_text("utf-8")


def test_r9_22_zalutali_zatvarajuci_tag_odbijen(tmp_path):
    wd, f = _wd(tmp_path, "<p><em>Ona je rekla</em> da ne ide.</p>")
    prije = f.read_text("utf-8")
    r = zavrsi.primijeni_u_html(wd / "checkpoints", _isp("rekla da ne ide", "rece da ne ide"),
                                log=lambda m: None)
    assert r["fail"] == 1 and r["ok"] == 0
    assert f.read_text("utf-8") == prije  # nista nije izmijenjeno


def test_r9_22_raspon_preko_odlomaka_odbijen_a_uravnotezen_prolazi(tmp_path):
    wd, f = _wd(tmp_path, "<p>Ona je rekla</p><p>da ne ide.</p>")
    prije = f.read_text("utf-8")
    r = zavrsi.primijeni_u_html(wd / "checkpoints", _isp("rekla da ne ide", "rece da ne ide"),
                                log=lambda m: None)
    assert r["fail"] == 1 and f.read_text("utf-8") == prije
    wd2, f2 = _wd(tmp_path / "b", "<p>Ona je <em>rekla</em> da ne ide.</p>")
    r2 = zavrsi.primijeni_u_html(wd2 / "checkpoints", _isp("Ona je rekla da ne ide", "Ona rece da ne ide"),
                                 log=lambda m: None)
    assert r2["ok"] == 1 and "<em>" not in f2.read_text("utf-8")


def test_r9_23_inline_tag_ne_razbija_rijec(tmp_path):
    epub = tmp_path / "k.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("c1.xhtml", "<html><body><p>Ona <em>rece</em> da ne i<b>de</b>.</p><p>Kraj</p></body></html>")
    r = zavrsi.provjeri_u_epubu(epub, [{"id": "t1", "novo": "Ona rece da ne ide"}])
    assert r == {"novo_u_epubu": 1, "nije_nadjeno": []}
    # blok tag i dalje razdvaja rijeci
    r2 = zavrsi.provjeri_u_epubu(epub, [{"id": "t2", "novo": "ide.Kraj"}])
    assert r2["nije_nadjeno"] == ["t2"]


def test_r9_24_vracanje_iz_backupa(tmp_path):
    wd, f = _wd(tmp_path, "<p>NOVO</p>")
    ck = wd / "checkpoints"
    (ck / "a.html_blok_0.chk").write_text("NOVO chk", encoding="utf-8")
    bdir = tmp_path / "bk"
    bdir.mkdir()
    (bdir / "a.html_blok_0.chk").write_text("STARO chk", encoding="utf-8")
    (bdir / "html_a.html").write_text("<html><body><p>STARO</p></body></html>", encoding="utf-8")
    rez = zavrsi._vrati_iz_backupa(bdir, ck, log=lambda m: None)
    assert rez == {"chk": 1, "html": 1}
    assert (ck / "a.html_blok_0.chk").read_text("utf-8") == "STARO chk"
    assert "STARO" in f.read_text("utf-8")
    assert zavrsi._vrati_iz_backupa(None, ck) == {"chk": 0, "html": 0}


def test_r9_24_pokreni_pao_vraca_chk(monkeypatch, tmp_path):
    monkeypatch.setattr(odluke, "PUTANJA", tmp_path / "o.jsonl")
    monkeypatch.setattr(zavrsi, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(zavrsi, "STATUS_FILE", tmp_path / "logs" / "st.json")
    monkeypatch.setattr(zavrsi, "ISPRAVCI", tmp_path / "isp")
    monkeypatch.setattr(zavrsi, "STATUS", {"stanje": "nema"})
    monkeypatch.setattr(zavrsi, "_backup_styled", lambda *a, **k: None)
    ck = tmp_path / "ck"
    ck.mkdir()
    (ck / "a.html_blok_0.chk").write_text("STARO", encoding="utf-8")

    def lazni_odluke(knjiga, ck_, bdir=None, dry=False, log=print):
        Path(bdir).mkdir(parents=True, exist_ok=True)
        (Path(bdir) / "a.html_blok_0.chk").write_text("STARO", encoding="utf-8")
        (ck_ / "a.html_blok_0.chk").write_text("NOVO", encoding="utf-8")
        return {"ok": 1, "vec": 0, "fail": 0}, [], []

    monkeypatch.setattr(zavrsi, "primijeni_odluke", lazni_odluke)
    monkeypatch.setattr(zavrsi, "_cmd", lambda cmd, log, timeout=None: (1, ""))
    st = zavrsi.pokreni("K", Path("/x/K.epub"), ck)
    assert st["stanje"] == "pao"
    assert (ck / "a.html_blok_0.chk").read_text("utf-8") == "STARO"
    assert st["vraceno"]["chk"] == 1


def test_r9_26_status_nova_referenca(monkeypatch):
    monkeypatch.setattr(zavrsi, "STATUS", {"stanje": "nema"})
    zavrsi._postavi_status({"stanje": "tece", "korak": "a"})
    prva = zavrsi.STATUS
    zavrsi._postavi_status({"stanje": "gotovo", "korak": "b"})
    assert prva == {"stanje": "tece", "korak": "a"}  # stara referenca nije mijenjana (nema clear())
    assert zavrsi.STATUS == {"stanje": "gotovo", "korak": "b"}
    assert zavrsi.status()["stanje"] == "gotovo"


def test_r9_28_vise_pogodaka_rglob_nije_izabrano(tmp_path):
    wd = tmp_path / "_skr_x"
    (wd / "checkpoints").mkdir(parents=True)
    for d in ("p1", "p2"):
        (wd / d).mkdir()
        (wd / d / "a.html").write_text("<p>Ona je rekla da ne ide.</p>", encoding="utf-8")
    r = zavrsi.primijeni_u_html(wd / "checkpoints", _isp("Ona je rekla da ne ide", "Ona rece da ne ide"),
                                log=lambda m: None)
    assert r["fail"] == 1 and r["ok"] == 0
    assert all("rece" not in (wd / d / "a.html").read_text("utf-8") for d in ("p1", "p2"))


def test_r9_25_putanje_iz_okoline(tmp_path):
    assert zavrsi._download_dir({"BOOKLYFI_DOWNLOAD_DIR": str(tmp_path / "dl")}) == tmp_path / "dl"
    assert isinstance(zavrsi._download_dir({}), Path)
    assert zavrsi._styled_dir().name  # config ili zadano, ne baca
