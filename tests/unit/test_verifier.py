# -*- coding: utf-8 -*-
"""Testovi za core/verifier.py (P2.1). Bez mreze i bez pytest-asyncio."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import verifier as V  # noqa: E402

EN = '<p class="x">He did not leave the city before 1840.</p><p>Savine had 3 sons.</p>'
HR = '<p>Napustio je grad prije 1840.</p><p>Savine je imala 3 sina.</p>'


def fl(odgovor, pozivi=None):
    """Mock fleet: vraca fiksni odgovor, biljezi (prompt, sys)."""
    def _f(prompt, sys_p):
        if pozivi is not None:
            pozivi.append((prompt, sys_p))
        return odgovor
    return _f


def js(**kw):
    return json.dumps(kw, ensure_ascii=False)


# ── osnovni tokovi ──────────────────────────────────────────────────────────
def test_cist_blok_ok():
    r = V.provjeri_blok(EN, HR, {}, fleet=fl('{"ok": true, "greske": []}'))
    assert r["ok"] is True and r["status"] == "ok" and r["provjeren"] is True
    assert r["greske"] == [] and r["score"] == 10.0 and r["error"] == ""


def test_model_s_greskama():
    odg = js(ok=False, greske=[
        {"tip": "negacija", "en_fragment": "did not leave",
         "hr_fragment": "Napustio je", "objasnjenje": "Negacija izgubljena."},
        {"tip": "broj", "en_fragment": "3 sons", "hr_fragment": "3 sina",
         "objasnjenje": "x"},
    ])
    r = V.provjeri_blok(EN, HR, {}, fleet=fl((odg, "GROQ")))
    assert r["ok"] is False and r["status"] == "greske" and r["provjeren"] is True
    assert [g["tip"] for g in r["greske"]] == ["negacija", "broj"]
    assert set(r["greske"][0]) == {"tip", "en_fragment", "hr_fragment", "objasnjenje"}
    assert r["model"] == "GROQ"
    assert r["score"] == round(10.0 - 3.0 - 2.0, 1)


def test_score_ne_pada_ispod_1():
    greske = [{"tip": "negacija"}] * 5
    assert V.izracunaj_score(greske) == 1.0


# ── prazan / malformed / nedostupan model ──────────────────────────────────
def test_prazan_odgovor_nije_ok():
    for prazan in ("", "   ", None, ("", "GEMINI")):
        r = V.provjeri_blok(EN, HR, {}, fleet=fl(prazan))
        assert r["ok"] is False and r["provjeren"] is False
        assert r["status"] == "neispravan_odgovor" and r["score"] is None


def test_malformed_json():
    for lose in ("ovo nije json {", '{"ok": tru', "[1,2,3]", '{"nesto": 1}'):
        r = V.provjeri_blok(EN, HR, {}, fleet=fl(lose))
        assert r["status"] == "neispravan_odgovor" and r["ok"] is False, lose


def test_greske_nije_lista():
    r = V.provjeri_blok(EN, HR, {}, fleet=fl('{"ok": false, "greske": "puno"}'))
    assert r["status"] == "neispravan_odgovor"


def test_nema_fleeta():
    r = V.provjeri_blok(EN, HR, {}, fleet=None)
    assert r["status"] == "nema_modela" and r["ok"] is False and r["provjeren"] is False


def test_izuzetak_u_fleetu():
    def bum(p, s):
        raise RuntimeError("429 quota")
    r = V.provjeri_blok(EN, HR, {}, fleet=bum)
    assert r["status"] == "greska_modela" and "429" in r["error"] and r["ok"] is False


def test_provider_content_filter():
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(("", "CONTENT_FILTER")))
    assert r["status"] == "greska_modela" and r["provjeren"] is False


def test_timeout_sync():
    def spor(p, s):
        time.sleep(0.5)
        return '{"ok": true, "greske": []}'
    t0 = time.time()
    r = V.provjeri_blok(EN, HR, {}, fleet=spor, timeout=0.05)
    assert r["status"] == "timeout" and r["ok"] is False
    assert time.time() - t0 < 0.4


def test_timeout_async():
    async def spor(p, s):
        await asyncio.sleep(0.5)
        return '{"ok": true, "greske": []}'
    r = asyncio.run(V.provjeri_blok_async(EN, HR, {}, fleet=spor, timeout=0.05))
    assert r["status"] == "timeout" and r["ok"] is False


# ── parsiranje ──────────────────────────────────────────────────────────────
def test_json_u_fenceu_i_out_omotacu():
    odg = '<out>\n```json\n{"ok": true, "greske": []}\n```\n</out>'
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(odg))
    assert r["status"] == "ok"


def test_json_okruzen_tekstom_i_zagrada_u_stringu():
    odg = ('Evo rezultata: {"ok": false, "greske": [{"tip": "kriv_smisao", '
           '"en_fragment": "before 1840", "hr_fragment": "prije 1840", '
           '"objasnjenje": "zagrada } u tekstu {"}]} hvala.')
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(odg))
    assert r["status"] == "greske" and r["greske"][0]["tip"] == "kriv_smisao"
    assert "}" in r["greske"][0]["objasnjenje"]


# ── integritet (P11) ────────────────────────────────────────────────────────
def test_halucinirana_prijava_se_odbacuje():
    odg = js(ok=False, greske=[{"tip": "negacija", "en_fragment": "never ever",
                                "hr_fragment": "nikada", "objasnjenje": "x"}])
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(odg))
    assert r["ok"] is True and r["status"] == "ok"
    assert r["greske"] == [] and r["odbaceno"] == 1


def test_izmisljeni_fragment_se_brise_ostali_ostaje():
    odg = js(ok=False, greske=[{"tip": "izostavljeno", "en_fragment": "before 1840",
                                "hr_fragment": "izmisljeno nesto", "objasnjenje": "x"}])
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(odg))
    g = r["greske"][0]
    assert g["en_fragment"] == "before 1840" and g["hr_fragment"] == ""


def test_fragment_normalizacija_navodnika_i_razmaka():
    en = '<p>He said “no”  twice.</p>'
    hr = '<p>Rekao je ne dvaput.</p>'
    odg = js(ok=False, greske=[{"tip": "dodano", "en_fragment": 'said "no" twice',
                                "hr_fragment": "", "objasnjenje": "x"}])
    r = V.provjeri_blok(en, hr, {}, fleet=fl(odg))
    assert r["status"] == "greske"


def test_ok_true_ali_ima_greske_pobjedjuju_greske():
    odg = js(ok=True, greske=[{"tip": "broj", "en_fragment": "3 sons",
                               "hr_fragment": "", "objasnjenje": "x"}])
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(odg))
    assert r["ok"] is False and r["status"] == "greske"


def test_ok_false_bez_detalja_nije_ok():
    r = V.provjeri_blok(EN, HR, {}, fleet=fl('{"ok": false, "greske": []}'))
    assert r["ok"] is False and r["status"] == "greske"
    assert r["greske"][0]["tip"] == "ostalo"


def test_nepoznat_tip_postaje_ostalo_i_dedup():
    g = {"tip": "NEŠTO", "en_fragment": "3 sons", "hr_fragment": "", "objasnjenje": "x"}
    r = V.provjeri_blok(EN, HR, {}, fleet=fl(js(ok=False, greske=[g, dict(g)])))
    assert len(r["greske"]) == 1 and r["greske"][0]["tip"] == "ostalo"


def test_ogranicenje_broja_gresaka():
    en = "<p>" + " ".join("w%d" % i for i in range(30)) + "</p>"
    greske = [{"tip": "dodano", "en_fragment": "w%d" % i, "hr_fragment": "",
               "objasnjenje": "x"} for i in range(30)]
    r = V.provjeri_blok(en, "<p>nesto</p>", {}, fleet=fl(js(ok=False, greske=greske)))
    assert len(r["greske"]) == V.MAX_GRESAKA


# ── ulaz / prompt ───────────────────────────────────────────────────────────
def test_prazan_ulaz_ne_zove_model():
    pozivi = []
    for en, hr in (("", HR), (EN, ""), ("<p> </p>", HR), (None, None)):
        r = V.provjeri_blok(en, hr, {}, fleet=fl('{"ok": true}', pozivi))
        assert r["status"] == "prazan_ulaz" and r["ok"] is False
    assert pozivi == []


def test_predug_blok_ne_zove_model():
    pozivi = []
    r = V.provjeri_blok("a" * (V.MAX_ZNAKOVA + 1), HR, {}, fleet=fl("{}", pozivi))
    assert r["status"] == "predug_blok" and pozivi == []


def test_prompt_cisti_html_i_filtrira_glosar():
    pozivi = []
    glosar = {"Savine": "Savine", "Orso": "Orso", "Leo": "Leo"}
    V.provjeri_blok(EN, HR, glosar, fleet=fl('{"ok": true, "greske": []}', pozivi))
    prompt, sys_p = pozivi[0]
    assert '<p class' not in prompt and "</p>" not in prompt
    assert "He did not leave the city" in prompt and "Napustio je grad" in prompt
    assert "Savine -> Savine" in prompt
    assert "Orso" not in prompt and "Leo" not in prompt
    assert "JSON" in sys_p


def test_bez_glosara_nema_sekcije():
    pozivi = []
    V.provjeri_blok(EN, HR, None, fleet=fl('{"ok": true}', pozivi))
    assert "GLOSAR" not in pozivi[0][0]


# ── async / adapter oblici ──────────────────────────────────────────────────
def test_async_api_i_async_fleet():
    async def f(p, s):
        return ('{"ok": true, "greske": []}', "GEMINI")
    r = asyncio.run(V.provjeri_blok_async(EN, HR, {}, fleet=f))
    assert r["status"] == "ok" and r["model"] == "GEMINI"


def test_async_api_sync_fleet_i_lambda_koja_vraca_coroutine():
    async def motor(p, s):
        return ('{"ok": true, "greske": []}', "GROQ")
    adapter = lambda p, s: motor(p, s)  # noqa: E731 — oblik pipeline adaptera
    r = asyncio.run(V.provjeri_blok_async(EN, HR, {}, fleet=adapter))
    assert r["status"] == "ok" and r["model"] == "GROQ"
    r2 = asyncio.run(V.provjeri_blok_async(EN, HR, {}, fleet=fl('{"ok": true}')))
    assert r2["status"] == "ok"


def test_sync_api_s_async_adapterom_unutar_event_loopa():
    async def motor(p, s):
        return '{"ok": true, "greske": []}'

    async def glavna():
        return V.provjeri_blok(EN, HR, {}, fleet=lambda p, s: motor(p, s))
    assert asyncio.run(glavna())["status"] == "ok"


def test_oblik_rezultata_uvijek_isti():
    kljucevi = {"ok", "status", "provjeren", "greske", "score", "model",
                "odbaceno", "error"}
    for f in (None, fl(""), fl('{"ok": true}'), fl("smece")):
        assert set(V.provjeri_blok(EN, HR, {}, fleet=f)) == kljucevi


# ── P2.1: oznaka_bloka ───────────────────────────────────────────────────────
def _rez(tipovi, provjeren=True):
    from core.verifier import izracunaj_score
    greske = [{"tip": x} for x in tipovi]
    return {"provjeren": provjeren, "greske": greske,
            "score": izracunaj_score(greske) if provjeren else None}


def test_oznaka_ok():
    from core.verifier import oznaka_bloka
    assert oznaka_bloka(_rez([])) == "ok"


def test_oznaka_neprovjeren():
    from core.verifier import oznaka_bloka
    assert oznaka_bloka(_rez([], provjeren=False)) == "neprovjeren"
    assert oznaka_bloka(None) == "neprovjeren"
    assert oznaka_bloka({}) == "neprovjeren"


def test_oznaka_kriv_smisao_je_sumnjiv_novo_pravilo():
    from core.verifier import oznaka_bloka
    r = {"provjeren": True, "score": 1.0, "greske": [{"tip": "kriv_smisao"}]}
    assert oznaka_bloka(r) == "sumnjiv"


def test_oznaka_score_ne_utjece():
    from core.verifier import oznaka_bloka
    for sc in (1.0, 6.9, 7.0, 9.5):
        r = {"provjeren": True, "score": sc, "greske": [{"tip": "kriv_smisao"}]}
        assert oznaka_bloka(r) == "sumnjiv"


def test_oznaka_los_negacija_i_broj():
    from core.verifier import oznaka_bloka
    for t in ("negacija", "broj"):
        r = {"provjeren": True, "score": 9.0, "greske": [{"tip": t}]}
        assert oznaka_bloka(r) == "los"







def test_oznaka_los_nizak_score():
    from core.verifier import oznaka_bloka
    assert oznaka_bloka(_rez(["broj", "broj"])) == "los"   # score 6.0
