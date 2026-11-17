"""L57: token za pristup s drugih uredaja + ogranicen file browser."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import app as app_mod

TOK = "tajna-test-123"
LAN = {"REMOTE_ADDR": "192.168.1.50"}


@pytest.fixture
def klijent():
    a = app_mod.create_app()
    a.config["TESTING"] = True
    with a.test_client() as c:
        yield c


def test_bez_tokena_u_okolini_sve_radi(klijent, monkeypatch):
    monkeypatch.delenv("BOOKLYFI_TOKEN", raising=False)
    assert klijent.get("/api/keys", environ_overrides=LAN).status_code == 200


def test_lan_bez_tokena_401(klijent, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_TOKEN", TOK)
    assert klijent.get("/api/keys", environ_overrides=LAN).status_code == 401


def test_lan_s_pogresnim_tokenom_401(klijent, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_TOKEN", TOK)
    r = klijent.get("/api/keys", headers={"X-Booklyfi-Token": "pogresan"}, environ_overrides=LAN)
    assert r.status_code == 401


def test_lan_s_headerom_prolazi(klijent, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_TOKEN", TOK)
    r = klijent.get("/api/keys", headers={"X-Booklyfi-Token": TOK}, environ_overrides=LAN)
    assert r.status_code == 200


def test_lan_query_token_postavlja_kolacic(klijent, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_TOKEN", TOK)
    r = klijent.get("/api/keys?token=" + TOK, environ_overrides=LAN)
    assert r.status_code == 200
    assert "booklyfi_token=" + TOK in r.headers.get("Set-Cookie", "")
    klijent.set_cookie("booklyfi_token", TOK)
    assert klijent.get("/api/keys", environ_overrides=LAN).status_code == 200


def test_loopback_ne_treba_token(klijent, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_TOKEN", TOK)
    assert klijent.get("/api/keys").status_code == 200  # test klijent = 127.0.0.1


def test_browse_ogranicen_na_korijene(klijent, monkeypatch, tmp_path):
    (tmp_path / "knjiga.epub").write_bytes(b"x")
    monkeypatch.setenv("BOOKLYFI_BROWSE_ROOTS", str(tmp_path))
    ok = klijent.post("/api/browse_files", json={"path": str(tmp_path)})
    assert ok.status_code == 200 and any(f["name"] == "knjiga.epub" for f in ok.get_json()["files"])
    assert klijent.post("/api/browse_files", json={"path": "/"}).status_code == 403
    assert klijent.post("/api/browse_files", json={"path": "/etc"}).status_code == 403
    traversal = str(tmp_path) + "/../../etc"
    assert klijent.post("/api/browse_files", json={"path": traversal}).status_code == 403


def test_upload_from_path_samo_iz_korijena(klijent, monkeypatch, tmp_path):
    import api.file_browser as fb

    src = tmp_path / "in"; src.mkdir(); (src / "a.epub").write_bytes(b"x")
    dest = tmp_path / "dest"; dest.mkdir()
    monkeypatch.setenv("BOOKLYFI_BROWSE_ROOTS", str(src))
    monkeypatch.setattr(fb, "INPUT_DIR", dest)
    assert klijent.post("/api/upload_from_path", json={"path": str(src / "a.epub")}).status_code == 200
    assert (dest / "a.epub").exists()
    izvan = tmp_path / "izvan.epub"; izvan.write_bytes(b"x")
    assert klijent.post("/api/upload_from_path", json={"path": str(izvan)}).status_code == 403
