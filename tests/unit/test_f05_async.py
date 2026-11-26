import ast
import asyncio
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SINKRONI = {
    "processing/workers.py": {"_qa_ai_ocjena", "_retry_s_feedbackom"},
    "processing/retro.py": {"_retry_s_feedbackom"},
    "processing/pipeline.py": {"formatiraj_za_prompt", "dodaj_odlican_prevod"},
    "network/http_client.py": {"_call_cloudflare_native", "_posalji_na_gemini_s_kontekstom"},
}


@pytest.mark.parametrize("rel", sorted(SINKRONI))
def test_nema_izravnih_sinkronih_poziva_u_async_funkcijama(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    nadjeno = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.AsyncFunctionDef):
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id in SINKRONI[rel]):
                    nadjeno.append((fn.name, n.func.id, n.lineno))
    assert nadjeno == []


def test_cloudflare_ne_blokira_petlju(monkeypatch):
    import network.http_client as hc

    def spor(*a, **k):
        time.sleep(0.6)
        return ("ok", "CLOUDFLARE")

    monkeypatch.setattr(hc, "_call_cloudflare_native", spor)

    class Fleet:
        def get_best_key(self, p):
            return "kljuc"

    class Self:
        fleet = Fleet()

    async def glavni():
        stanje = {"otkucaji": 0, "gotovo": False}

        async def sat():
            while not stanje["gotovo"]:
                await asyncio.sleep(0.05)
                stanje["otkucaji"] += 1

        t = asyncio.create_task(sat())
        res = await hc._call_single_provider(Self(), "CLOUDFLARE", "m", "s", "u", 0.3)
        stanje["gotovo"] = True
        await t
        return res, stanje["otkucaji"]

    res, otkucaji = asyncio.run(glavni())
    assert res == ("ok", "CLOUDFLARE")
    assert otkucaji >= 6


def test_glosar_poredak_iz_prioriteta():
    from config.ai_config import PROVIDER_PRIORITY
    from core import glosar_ekstrakcija as ge

    redom = []

    class Fleet:
        def get_best_key(self, p):
            redom.append(p)
            return None

    ge.posalji_ai_batch("EN", ["Orso"], Fleet())
    ocekivano = [p for p in PROVIDER_PRIORITY["GLOSAR_UPDATE"] if p != "GEMMA"]
    assert redom[: len(ocekivano)] == ocekivano
    assert "GEMMA" not in redom


def test_few_shot_istodobno_pisanje(tmp_path, monkeypatch):
    from core import few_shot_global as fs

    monkeypatch.setattr(fs, "FEW_SHOT_PATH", tmp_path / "fs.json")
    niti = [
        threading.Thread(target=fs.dodaj_odlican_prevod,
                         args=(chr(65 + i) * 50, "prijevod " + str(i), 9.5, "narativ"))
        for i in range(8)
    ]
    for n in niti:
        n.start()
    for n in niti:
        n.join()
    assert len(fs.load_shots()) == 8
