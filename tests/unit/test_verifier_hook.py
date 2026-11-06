# -*- coding: utf-8 -*-
import asyncio
import json
from pathlib import Path

from processing import verifier_hook as vh

EN = "<p>He did not go to the city.</p>"
HR = "<p>Otišao je u grad.</p>"


class _Fake:
    def __init__(self, tmp, odgovor=None, greska=None):
        self.checkpoint_dir = Path(tmp)
        self.odgovor = odgovor
        self.greska = greska
        self.pozivi = []
        self.logovi = []

    async def _call_ai_engine(self, prompt, chunk_idx, uloga="LEKTOR", filename="",
                              sys_override=None, tip_bloka="naracija"):
        self.pozivi.append({"uloga": uloga, "sys": sys_override, "idx": chunk_idx})
        if self.greska:
            raise self.greska
        return self.odgovor, "GROQ"

    def _atomic_write(self, p, txt):
        Path(p).write_text(txt, "utf-8")

    def log(self, msg, lvl="info"):
        self.logovi.append((lvl, msg))


def _run(fake, original=EN):
    return asyncio.run(vh.verifikuj_blok(fake, HR, original, "f_blok_1", 1, "f", "naracija", {}))


def test_iskljucen_po_defaultu(tmp_path, monkeypatch):
    monkeypatch.delenv("BOOKLYFI_VERIFIER", raising=False)
    f = _Fake(tmp_path, '{"ok": true, "greske": []}')
    assert _run(f) is None
    assert not f.pozivi
    assert not (tmp_path / "quality_verifier.json").exists()


def test_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_VERIFIER", "1")
    f = _Fake(tmp_path, '{"ok": true, "greske": []}')
    assert _run(f) == {"verifier": "ok"}
    d = json.loads((tmp_path / "quality_verifier.json").read_text("utf-8"))
    assert d["f_blok_1"] == {"verifier": "ok"}


def test_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_VERIFIER", "1")
    odg = json.dumps({"ok": False, "greske": [{
        "tip": "negacija", "en_fragment": "did not go", "hr_fragment": "Otišao je",
        "objasnjenje": "negacija izgubljena"}]})
    f = _Fake(tmp_path, odg)
    r = _run(f)
    assert r["verifier"] == "flags" and r["n"] >= 1
    assert any(l == "warning" for l, _ in f.logovi)


def test_greska_modela_ne_ruši(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_VERIFIER", "1")
    f = _Fake(tmp_path, greska=RuntimeError("x"))
    r = _run(f)
    assert r["verifier"] == "skip"


def test_uloga_i_sys_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_VERIFIER", "1")
    f = _Fake(tmp_path, '{"ok": true, "greske": []}')
    _run(f)
    assert f.pozivi[0]["uloga"] == "SCORER"
    assert f.pozivi[0]["sys"]


def test_bez_originala(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_VERIFIER", "1")
    f = _Fake(tmp_path, '{"ok": true, "greske": []}')
    assert _run(f, original=None) is None
    assert not f.pozivi
