import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tests.unit.test_g16_pomocne import _Engine, _QT


def _pokreni(monkeypatch, tmp_path, uloga, odgovori):
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
    res = asyncio.run(pr._call_ai_engine(_Engine(), "p", 11, uloga=uloga, sys_override="s"))
    return res, pozvani


def test_prevodilac_google_pada_groq_spasava(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKLYFI_STRICT_GEMINI", "1")
    monkeypatch.delenv("BOOKLYFI_ZADNJA_LINIJA", raising=False)
    res, pozvani = _pokreni(monkeypatch, tmp_path, "PREVODILAC", {"GROQ": "prijevod"})
    assert res[0] == "prijevod"
    assert pozvani[-1] == "GROQ"


def test_zadnja_linija_se_moze_ugasiti(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKLYFI_ZADNJA_LINIJA", "0")
    res, pozvani = _pokreni(monkeypatch, tmp_path, "KOREKTOR", {"GROQ": "x"})
    assert res == (None, "ALL_FAILED")
    assert "GROQ" not in pozvani
