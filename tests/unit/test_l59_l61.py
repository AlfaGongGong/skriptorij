import json
import logging
import re
from pathlib import Path


def test_redaktiraj_url_i_tokeni():
    from utils.redakt import redaktiraj
    s = ("GET https://x/v1beta/models/g:generateContent?key=AIzaSyABCDEFGHIJKLMNOPQRSTUV&alt=1 "
         "Bearer abcdefgh12345 gsk_abcdefghijklmnop1234")
    r = redaktiraj(s)
    assert "AIzaSy" not in r and "abcdefgh12345" not in r and "gsk_abcdefghijklmnop1234" not in r
    assert "?key=***" in r and "&alt=1" in r


def test_log_tvornica_redaktira():
    from utils.redakt import instaliraj_redaktor
    instaliraj_redaktor()
    instaliraj_redaktor()
    r = logging.getLogger("t").makeRecord("t", logging.INFO, "f", 1, "url %s", ("?key=TAJNA123456",), None)
    assert "TAJNA123456" not in r.getMessage()


def test_build_headers_gemini_koristi_header():
    from network.http_client import _build_headers
    h = _build_headers("GEMINI", "kljuc123")
    assert h["x-goog-api-key"] == "kljuc123"
    assert "Authorization" not in h


def test_nema_kljuca_u_url_u_kodu():
    root = Path(__file__).resolve().parents[2]
    rx = re.compile(r'f"[^"\n]*\?key=\{')
    for rel in ("network/http_client.py", "network/model_discovery.py", "app.py"):
        t = (root / rel).read_text(encoding="utf-8")
        assert not rx.search(t), rel


def test_atomic_write_text_bez_tmp_ostataka(tmp_path):
    from utils.file_utils import atomic_write_text
    p = tmp_path / "a.json"
    atomic_write_text(p, "x")
    atomic_write_text(p, "y")
    assert p.read_text(encoding="utf-8") == "y"
    assert list(tmp_path.glob("*.tmp")) == []


def test_zavrsi_spremi_atomski(tmp_path, monkeypatch):
    import core.zavrsi as Z
    monkeypatch.setattr(Z, "LOGS", tmp_path)
    monkeypatch.setattr(Z, "STATUS_FILE", tmp_path / "s.json")
    Z._spremi({"stanje": "x", "naslov": "\u010d"})
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["stanje"] == "x"
    assert list(tmp_path.glob("*.tmp")) == []
