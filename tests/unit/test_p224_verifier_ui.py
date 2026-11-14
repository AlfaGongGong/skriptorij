from core.verifier import sazetak_oznaka


def test_sazetak_oznaka():
    d = {
        "a_blok_0": {"verifier": "ok", "oznaka": "ok"},
        "a_blok_1": {"verifier": "flags", "oznaka": "los"},
        "a_blok_2": {"verifier": "flags", "oznaka": "sumnjiv"},
        "a_blok_3": {"verifier": "skip", "oznaka": "neprovjeren"},
        "a_blok_4": {"verifier": "ok"},
        "a_blok_5": {"verifier": "skip"},
        "a_blok_6": {"verifier": "flags"},
    }
    r = sazetak_oznaka(d)
    assert (r["ukupno"], r["ok"], r["sumnjiv"], r["los"], r["neprovjeren"], r["provjereno"]) == (7, 2, 2, 1, 2, 5)


def test_prazno_i_krivo():
    assert sazetak_oznaka({})["ukupno"] == 0
    assert sazetak_oznaka(None)["provjereno"] == 0
