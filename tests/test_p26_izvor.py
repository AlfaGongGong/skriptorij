from pathlib import Path

import pytest

P = pytest.importorskip("api.routes.processing", reason="processing.py se ne moze uvesti")


def _pripremi(monkeypatch, tmp_path, clean):
    inp, org, dl = tmp_path / "in", tmp_path / "orig", tmp_path / "dl"
    for d in (inp, org, dl):
        d.mkdir()
    monkeypatch.setattr(P, "INPUT_DIR", inp)
    monkeypatch.setattr(P, "_P26_ORIGINALI", org)
    monkeypatch.setattr(P, "_P26_DOWNLOAD", dl)
    monkeypatch.setattr(P, "SHARED_STATS", {})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path / "nema")
    monkeypatch.setattr(P, "_p26_knjiga", lambda: clean)
    return inp, org, dl


def test_tocno_ime_ima_prednost(monkeypatch, tmp_path):
    inp, org, dl = _pripremi(monkeypatch, tmp_path, "Delacroix")
    (org / "Stephen_King_Delacroix_dugo_ime.epub").write_bytes(b"x")
    (org / "Delacroix.epub").write_bytes(b"x")
    (org / "Delacroix_PREVEDENO_STYLED.epub").write_bytes(b"x")
    assert P._p26_izvorni_epub().name == "Delacroix.epub"


def test_rijeci_iz_imena_i_isklucuje_prevedeno(monkeypatch, tmp_path):
    inp, org, dl = _pripremi(monkeypatch, tmp_path, "The_Bad_Death")
    (dl / "styled_bak_The_Bad_Death_1.epub").write_bytes(b"x")
    (dl / "The Bad Death_PREVEDENO.epub").write_bytes(b"x")
    (dl / "xx_the_bad_death_xx.epub").write_bytes(b"x")
    assert P._p26_izvorni_epub().name == "xx_the_bad_death_xx.epub"


def test_nema_izvora(monkeypatch, tmp_path):
    _pripremi(monkeypatch, tmp_path, "Nepostojeca")
    assert P._p26_izvorni_epub() is None


def test_revizija_html_jinja_sigurna_i_ima_gumbe():
    s = (Path(__file__).resolve().parent.parent / "templates" / "revizija.html").read_text("utf-8")
    for opasno in ("{{", "{%", "{#"):
        assert opasno not in s, f"Jinja-opasan niz {opasno!r} u revizija.html"
    for ide in ('id="b-zavrsi"', 'id="b-zavrsi-dry"', 'id="z-status"', "/api/review/zavrsi/status"):
        assert ide in s
