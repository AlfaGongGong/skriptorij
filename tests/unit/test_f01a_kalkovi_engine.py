from pathlib import Path

import core.kalkovi as K
from core.kalkovi.engine import KalkoviEngine, kalkovi_engine

KOREN = Path(__file__).resolve().parents[2]


def _p(t):
    return kalkovi_engine.primijeni(t)[0]


def test_veliko_pocetno_slovo():
    assert _p("Deca su igrala.").startswith("Djeca su")
    assert _p("Ceo dan je radio.").startswith("Cijeli dan")
    assert _p("Ko je to?").startswith("Tko je to")
    assert _p("<p>Ceo dan.</p>") == "<p>Cijeli dan.</p>"
    assert _p("ceo dan").startswith("cijeli dan")


def test_sve_velikim_slovima():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    assert e.primijeni("DECA")[0] == "DJECA"
    assert e.primijeni("Deca")[0] == "Djeca"
    assert e.primijeni("deca")[0] == "djeca"


def test_reload_ne_prazni_engine():
    n = K.reload_dinamicki_kalkove()
    assert n >= 500
    assert kalkovi_engine.broj_patterna == n
    assert _p("Deca su igrala.").startswith("Djeca")


def test_neispravni_unosi_i_reload():
    e = KalkoviEngine([("a", "b"), (), ("(", "x"), ("c",)])
    assert e.broj_patterna == 1
    e.reload([(), ()])
    assert e.broj_patterna == 1
    e.reload([("x", "y")])
    assert e.primijeni("x")[0] == "y"


def test_identicne_zamjene_se_ne_broje():
    e = KalkoviEngine([("abc", "abc")])
    assert e.primijeni("abc abc") == ("abc abc", 0)


def test_dinamicki_samo_cijele_rijeci():
    assert _p("Detektiv je došao.") == "Detektiv je došao."
    assert _p("Deterdžent") == "Deterdžent"
    assert _p("Uopšteno govoreći") == "Općenito govoreći"
    assert _p("porodicama") == "obiteljima"
    assert _p("Mislim da dam.") == "Mislim da dam."
    assert _p("Porodično stablo") == "Porodično stablo"


def test_lista_bez_kvarnih_pravila():
    from core.kalkovi.dinamicki_lista import DINAMICKI_KALKOVI as L

    for p, z in L:
        assert p != z, p
    assert ("porodično", "obiteljski") not in L
    assert ("mislim da je bolje da", "mislim da je bolje") not in L


def test_retro_pise_samo_promijenjeno():
    src = (KOREN / "processing" / "retro.py").read_text(encoding="utf-8")
    assert "tekst_kor != tekst_orig" in src
