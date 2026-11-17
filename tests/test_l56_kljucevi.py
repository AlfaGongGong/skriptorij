"""L56: dodavanje/brisanje API kljuceva ne smije unistiti dev_api.json."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import app as app_mod


class _LazniFleet:
    def reload(self):
        pass


@pytest.fixture
def klijent(tmp_path, monkeypatch):
    cfg = tmp_path / "dev_api.json"
    monkeypatch.setattr(app_mod, "_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(app_mod, "_get_fleet", lambda: _LazniFleet())
    a = app_mod.create_app()
    a.config["TESTING"] = True
    with a.test_client() as c:
        yield c, cfg


def _dodaj(c, prov, key):
    return c.post("/api/keys/" + prov, json={"key": key})


def test_dodaj_cuva_ostale_i_pravi_bak(klijent):
    c, cfg = klijent
    pocetno = {"GEMINI": ["AIzaStari0001"], "GROQ": ["gsk_staro0002"]}
    cfg.write_text(json.dumps(pocetno), "utf-8")
    r = _dodaj(c, "gemini", "AIzaNovi00003")
    assert r.status_code == 200
    d = json.loads(cfg.read_text("utf-8"))
    assert d["GEMINI"] == ["AIzaStari0001", "AIzaNovi00003"]
    assert d["GROQ"] == ["gsk_staro0002"]
    assert json.loads((tmp := cfg.with_suffix(".json.bak")).read_text("utf-8")) == pocetno
    assert not cfg.with_suffix(".json.tmp").exists()


def test_neispravan_json_nikad_se_ne_prepisuje(klijent):
    c, cfg = klijent
    pokvaren = '{"GEMINI": ["AIzaStari0001", "AIza'  # prekinut zapis
    cfg.write_text(pokvaren, "utf-8")
    r = _dodaj(c, "GEMINI", "AIzaNovi00003")
    assert r.status_code == 409
    assert cfg.read_text("utf-8") == pokvaren
    assert not cfg.with_suffix(".json.bak").exists()


def test_bak_se_ne_prepisuje_pokvarenim_fajlom(klijent):
    c, cfg = klijent
    dobar = {"GEMINI": ["AIzaStari0001"]}
    cfg.write_text(json.dumps(dobar), "utf-8")
    assert _dodaj(c, "GEMINI", "AIzaNovi00003").status_code == 200
    cfg.write_text("{pokvareno", "utf-8")
    assert _dodaj(c, "GEMINI", "AIzaNovi00004").status_code == 409
    assert json.loads(cfg.with_suffix(".json.bak").read_text("utf-8")) == dobar


def test_dodaj_kad_fajl_ne_postoji(klijent):
    c, cfg = klijent
    assert not cfg.exists()
    assert _dodaj(c, "GEMINI", "AIzaNovi00003").status_code == 200
    assert json.loads(cfg.read_text("utf-8")) == {"GEMINI": ["AIzaNovi00003"]}


def test_brisanje_cuva_ostale(klijent):
    c, cfg = klijent
    pocetno = {"GEMINI": ["AIzaA0000001", "AIzaB0000002"], "GROQ": ["gsk_c0000003"]}
    cfg.write_text(json.dumps(pocetno), "utf-8")
    r = c.delete("/api/keys/gemini/0")
    assert r.status_code == 200
    d = json.loads(cfg.read_text("utf-8"))
    assert d["GEMINI"] == ["AIzaB0000002"] and d["GROQ"] == ["gsk_c0000003"]
    assert json.loads(cfg.with_suffix(".json.bak").read_text("utf-8")) == pocetno


def test_brisanje_neispravan_json_409_bez_izmjene(klijent):
    c, cfg = klijent
    cfg.write_text("{pokvareno", "utf-8")
    r = c.delete("/api/keys/gemini/0")
    assert r.status_code == 409
    assert cfg.read_text("utf-8") == "{pokvareno"
