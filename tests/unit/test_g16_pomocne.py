import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

from config.ai_config import MODEL_MAP


class _Key:
    def __init__(self, k):
        self.key = k
        self.success_rate = 1.0


class _Fleet:
    def __init__(self):
        self.fleet = {p: [_Key("K_" + p)] for p in ("GEMINI", "GROQ", "NVIDIA", "GEMMA")}

    def get_best_key(self, prov):
        k = self.fleet.get(prov)
        return k[0] if k else None

    def has_available_key(self, prov):
        return bool(self.fleet.get(prov))

    def get_active_model(self, prov, default=None):
        return MODEL_MAP.get(prov, default or "m")


class _Engine:
    def __init__(self):
        self.fleet = _Fleet()
        self.shared_controls = {}
        self.logovi = []

    def log(self, msg, level="info"):
        self.logovi.append(msg)


class _QT:
    def is_key_available(self, provider, key):
        return True, ""


def _pokreni(monkeypatch, uloga, odgovori, tmp_path):
    import network.provider_router as pr

    pozvani = []

    async def lazni(self_obj, prov, model, sys_c, prompt, temp, max_tokens=2400):
        pozvani.append(prov)
        r = odgovori.get(prov)
        return (r, prov + "-" + model) if r else (None, None)

    async def bez_sna(_s):
        pass

    monkeypatch.setattr(pr, "_call_single_provider", lazni)
    monkeypatch.setattr("network.quota_tracker.quota_tracker", _QT())
    monkeypatch.setattr("asyncio.sleep", bez_sna)
    monkeypatch.setenv("BOOKLYFI_AI_STAT", str(tmp_path / "stat.json"))
    res = asyncio.run(pr._call_ai_engine(_Engine(), "p", 0, uloga=uloga, sys_override="s"))
    return res, pozvani


def test_scorer_ne_dira_gemini_i_nema_drugog_kruga(monkeypatch, tmp_path):
    monkeypatch.delenv("BOOKLYFI_AUX_GEMINI", raising=False)
    res, pozvani = _pokreni(monkeypatch, "SCORER", {}, tmp_path)
    assert res == (None, "ALL_FAILED")
    assert "GEMINI" not in pozvani
    assert "GROQ" in pozvani
    # 4 pokusaja x (GROQ, NVIDIA, GEMMA), bez 2. i 3. kruga
    assert len(pozvani) <= 12


def test_verifier_prelazi_na_gemmu_ne_na_gemini(monkeypatch, tmp_path):
    monkeypatch.delenv("BOOKLYFI_AUX_GEMINI", raising=False)
    res, pozvani = _pokreni(monkeypatch, "VERIFIER", {"GEMMA": "OK"}, tmp_path)
    assert res[0] == "OK"
    assert "GEMINI" not in pozvani


def test_jezicna_uloga_ostaje_na_gemini(monkeypatch, tmp_path):
    monkeypatch.delenv("BOOKLYFI_AUX_GEMINI", raising=False)
    res, pozvani = _pokreni(monkeypatch, "PREVODILAC", {"GEMINI": "PRIJEVOD"}, tmp_path)
    assert res[0] == "PRIJEVOD"
    assert pozvani[0] == "GEMINI"


def test_aux_gemini_prekidac_vraca_staro(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKLYFI_AUX_GEMINI", "1")
    res, pozvani = _pokreni(monkeypatch, "SCORER", {"GEMINI": "OK"}, tmp_path)
    assert res[0] == "OK"
    assert "GEMINI" in pozvani


def test_statistika_se_biljezi(monkeypatch, tmp_path):
    import json

    import network.provider_router as pr

    monkeypatch.delenv("BOOKLYFI_AUX_GEMINI", raising=False)
    _pokreni(monkeypatch, "SCORER", {"GROQ": "OK"}, tmp_path)
    _pokreni(monkeypatch, "SCORER", {}, tmp_path)
    pr._g16_flush()
    d = json.loads((tmp_path / "stat.json").read_text("utf-8"))
    assert d["SCORER|GROQ"]["ok"] >= 1
    assert d["SCORER|ALL_FAILED"]["fail"] >= 1
