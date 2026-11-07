from core.verifier import oznaka_bloka


def _r(tipovi, score=3.0, prov=True):
    return {"provjeren": prov, "score": score, "greske": [{"tip": t} for t in tipovi]}


def test_kriv_smisao_sam_je_sumnjiv_bez_obzira_na_score():
    assert oznaka_bloka(_r(["kriv_smisao"], score=1.0)) == "sumnjiv"
    assert oznaka_bloka(_r(["kriv_smisao", "kriv_smisao"], score=2.0)) == "sumnjiv"


def test_tezki_tipovi_su_los():
    for t in ("negacija", "broj", "izostavljeno", "dodano", "ime"):
        assert oznaka_bloka(_r([t], score=9.0)) == "los"


def test_mjesano_je_los():
    assert oznaka_bloka(_r(["kriv_smisao", "broj"])) == "los"


def test_bez_gresaka_ok_i_neprovjeren():
    assert oznaka_bloka(_r([], score=1.0)) == "ok"
    assert oznaka_bloka(_r([], prov=False)) == "neprovjeren"
    assert oznaka_bloka(None) == "neprovjeren"
