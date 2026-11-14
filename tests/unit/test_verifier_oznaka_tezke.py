import importlib

import core.verifier as V
from core.verifier import oznaka_bloka, sazetak_oznaka


def _r(tipovi, score=3.0, prov=True):
    return {"provjeren": prov, "score": score, "greske": [{"tip": t} for t in tipovi]}


def test_kriv_smisao_sam_je_sumnjiv_bez_obzira_na_score():
    assert oznaka_bloka(_r(["kriv_smisao"], score=1.0)) == "sumnjiv"
    assert oznaka_bloka(_r(["kriv_smisao", "kriv_smisao"], score=2.0)) == "sumnjiv"


def test_los_su_negacija_broj_ime():
    for t in ("negacija", "broj", "ime"):
        assert oznaka_bloka(_r([t], score=9.0)) == "los"


def test_dodano_izostavljeno_su_sumnjivi():
    for t in ("dodano", "izostavljeno"):
        assert oznaka_bloka(_r([t], score=9.0)) == "sumnjiv"


def test_mjesano_je_los():
    assert oznaka_bloka(_r(["kriv_smisao", "broj"])) == "los"
    assert oznaka_bloka(_r(["dodano", "ime"])) == "los"


def test_strogo_vraca_staro(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_OZNAKA_STROGO", "1")
    for t in ("negacija", "broj", "izostavljeno", "dodano", "ime"):
        assert oznaka_bloka(_r([t])) == "los"


def test_bez_gresaka_ok_i_neprovjeren():
    assert oznaka_bloka(_r([], score=1.0)) == "ok"
    assert oznaka_bloka(_r([], prov=False)) == "neprovjeren"
    assert oznaka_bloka(None) == "neprovjeren"


def test_sazetak_preracunava_staru_oznaku_iz_gresaka():
    d = {
        "a_blok_0": {"verifier": "flags", "oznaka": "los", "greske": [{"tip": "dodano"}]},
        "a_blok_1": {"verifier": "flags", "oznaka": "los", "greske": [{"tip": "broj"}]},
        "a_blok_2": {"verifier": "ok", "oznaka": "ok"},
    }
    r = sazetak_oznaka(d)
    assert (r["los"], r["sumnjiv"], r["ok"]) == (1, 1, 1)
