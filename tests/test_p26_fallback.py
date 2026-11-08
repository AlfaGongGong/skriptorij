import os
import time
from pathlib import Path

import pytest

P = pytest.importorskip("api.routes.processing", reason="processing.py se ne moze uvesti")


def _verifier(root, ime, starost):
    d = root / f"_skr_{ime}" / "checkpoints"
    d.mkdir(parents=True)
    f = d / "quality_verifier.json"
    f.write_text("{}", "utf-8")
    t = time.time() - starost
    os.utime(f, (t, t))


def test_fallback_uzima_najnoviji_verifier(monkeypatch, tmp_path):
    root = tmp_path / "ck"
    _verifier(root, "Stara_Knjiga", 5000)
    _verifier(root, "Delacroix", 10)
    monkeypatch.setattr(P, "CHECKPOINT_BASE_DIR", root)
    monkeypatch.setattr(P, "SHARED_STATS", {"current_file": "---"})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    assert P._p26_knjiga() == "Delacroix"


def test_aktivna_knjiga_ima_prednost(monkeypatch, tmp_path):
    root = tmp_path / "ck"
    _verifier(root, "Delacroix", 10)
    monkeypatch.setattr(P, "CHECKPOINT_BASE_DIR", root)
    monkeypatch.setattr(P, "SHARED_STATS", {"current_file": "A_Death.epub"})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    assert P._p26_knjiga() == "A_Death"


def test_fallback_bez_ijednog_verifiera(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "CHECKPOINT_BASE_DIR", tmp_path / "nema")
    monkeypatch.setattr(P, "SHARED_STATS", {"current_file": "---"})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    assert P._p26_knjiga() == ""


def test_ai_prevedi_koristi_kopiju_pod_imenom_knjige(monkeypatch, tmp_path):
    eng = pytest.importorskip("core.engine", reason="core.engine se ne moze uvesti")
    izvor = tmp_path / "The Bad Death -- Stephen King -- Anna's Archive.epub"
    izvor.write_bytes(b"x")

    class Lazni:
        zadnji = None
        postojao = False

        def __init__(self, book_path, model, ss, sc):
            Lazni.zadnji = Path(book_path)
            Lazni.postojao = Path(book_path).exists()

        async def _call_ai_engine(self, prompt, br, **kw):
            return ("novi tekst", "M")

    monkeypatch.setattr(eng, "SkriptorijAllInOne", Lazni)
    monkeypatch.setattr(P, "SHARED_STATS", {})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(P, "_p26_knjiga", lambda: "Delacroix")
    monkeypatch.setattr(P, "_p26_izvorni_epub", lambda: izvor)
    assert P._p26_ai_prevedi("prompt", 1, "part1.html_blok_0") == "novi tekst"
    assert Lazni.zadnji.name == "Delacroix.epub" and Lazni.postojao
    assert not Lazni.zadnji.exists(), "privremena kopija nije obrisana"
    assert izvor.exists()


def test_ai_prevedi_bez_izvora(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "SHARED_STATS", {})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(P, "_p26_knjiga", lambda: "Delacroix")
    monkeypatch.setattr(P, "_p26_izvorni_epub", lambda: None)
    with pytest.raises(RuntimeError):
        P._p26_ai_prevedi("p", 1, "b")


def test_revizija_html_prikazuje_knjigu_i_jinja_sigurna():
    s = (Path(__file__).resolve().parent.parent / "templates" / "revizija.html").read_text("utf-8")
    assert 'r.push("Knjiga: " + s.knjiga)' in s
    for opasno in ("{{", "{%", "{#"):
        assert opasno not in s
