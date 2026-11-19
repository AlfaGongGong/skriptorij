"""G10: V2 rezultat prolazi kapije kao V1; odbijen -> fallback na V1."""
import asyncio

import processing.pipeline as P

EN = (
    "<p>The old man walked slowly down the road, and the wind was cold in 1843.</p>"
    "<p>They walked on until the night came, and Katherine did not speak again.</p>"
)
DOBAR = (
    "<p>Starac je polako hodao cestom, a vjetar je bio hladan 1843. godine.</p>"
    "<p>Hodali su dok nije pala noć, a Katherine nije više progovorila.</p>"
)
LOSE = DOBAR.replace("1843", "1834")  # G3: promijenjen broj


class Lazni:
    def __init__(self):
        self.logs = []
        self.kvota_stop = False

    def log(self, msg, lvl="info", **kw):
        self.logs.append(msg)

    def _extract_relevant_glossary(self, chunk):
        return ""


def _run(c):
    return asyncio.run(c)


def test_dobar_tekst_prolazi():
    r, t = _run(P._v2_kapije(Lazni(), EN, DOBAR, "f", 0))
    assert r is None and t == DOBAR


def test_g3_odbija_promijenjen_broj():
    r, _ = _run(P._v2_kapije(Lazni(), EN, LOSE, "f", 0))
    assert r and "G3" in r


def test_engleski_tekst_odbijen():
    r, _ = _run(P._v2_kapije(Lazni(), EN, EN, "f", 0))
    assert r


def _retry(monkeypatch, v2_tekst):
    class W:
        def __init__(self, **kw):
            pass

        def obradi_chunk(self, chunk):
            return {"success": True, "tekst": v2_tekst, "provider": "x", "model_ime": "m", "quality_score": 9}

    pozivi = {"v1": 0, "chk": 0}

    async def v1(self, *a, **k):
        pozivi["v1"] += 1
        return "<p>V1</p>", "V1ENG"

    def chk(*a, **k):
        pozivi["chk"] += 1

    self = Lazni()
    self._get_chapter_summary_for_lektor = lambda f: ""
    self.global_done_chunks = 0
    self.stvarno_prevedeno_u_sesiji = 0
    self.shared_stats = {}
    monkeypatch.setattr(P, "USE_WORKERS_V2", True)
    monkeypatch.setattr(P, "_V2_DOSTUPAN", True)
    monkeypatch.setattr(P, "WorkerV2", W)
    monkeypatch.setattr(P, "process_chunk_with_ai", v1)
    monkeypatch.setattr(P, "_chk_write", chk)

    async def qs(*a, **k):
        return None

    monkeypatch.setattr(P, "_quality_scoring", qs)
    out = _run(P.process_chunk_with_retry(self, EN, "", "", 0, "f"))
    return out, pozivi, self


def test_odbijen_v2_pada_na_v1(monkeypatch):
    out, p, _ = _retry(monkeypatch, LOSE)
    assert out == ("<p>V1</p>", "V1ENG") and p["v1"] == 1 and p["chk"] == 0


def test_dobar_v2_upisuje(monkeypatch):
    out, p, _ = _retry(monkeypatch, DOBAR)
    assert out[0] == DOBAR and p["v1"] == 0 and p["chk"] == 1
