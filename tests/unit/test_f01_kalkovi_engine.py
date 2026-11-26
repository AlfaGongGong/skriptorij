"""F01a: ponašanje KalkoviEngine-a (R11a-1/3/8/11/18/22/23). Sintetičke liste, bez stvarnih pravila."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.kalkovi import engine as E  # noqa: E402
from core.kalkovi.engine import KalkoviEngine  # noqa: E402


def test_veliko_pocetno_slovo_i_sve_velika():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    assert e.primijeni("Deca igraju.")[0] == "Djeca igraju."
    assert e.primijeni("deca igraju.")[0] == "djeca igraju."
    assert e.primijeni("DECA")[0] == "DJECA"


def test_fraza_cuva_veliko_slovo():
    e = KalkoviEngine([(r"\bceo dan\b", "cijeli dan"), (r"\bko je\b", "tko je")])
    assert e.primijeni("Ceo dan je kišio.")[0] == "Cijeli dan je kišio."
    assert e.primijeni("Ko je to?")[0] == "Tko je to?"
    assert e.primijeni("ceo dan")[0] == "cijeli dan"


def test_html_tagovi_se_ne_diraju():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    izlaz, n = e.primijeni('<p class="deca">Deca</p>')
    assert izlaz == '<p class="deca">Djeca</p>'
    assert n == 1
    assert e.primijeni("<p>Ceo dan.</p>")[0] == "<p>Ceo dan.</p>"


def test_identicne_zamjene_se_ne_broje():
    e = KalkoviEngine([(r"\bdan\b", "dan")])
    izlaz, n = e.primijeni("Dan i dan.")
    assert izlaz == "Dan i dan."
    assert n == 0
    assert e.statistike()["zamjene_po_kategoriji"] == {}


def test_reload_s_neispravnom_listom_ne_prazni_engine():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    assert e.broj_patterna == 1
    e.reload([()])
    assert e.broj_patterna == 1
    e.reload([("(", "x")])
    assert e.broj_patterna == 1
    assert e.primijeni("deca")[0] == "djeca"


def test_reload_s_valjanom_listom_zamjenjuje_patterne():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    e.reload([(r"\bko\b", "tko")])
    assert e.broj_patterna == 1
    assert e.primijeni("deca")[0] == "deca"
    assert e.primijeni("ko")[0] == "tko"


def test_neispravni_unosi_se_preskacu():
    e = KalkoviEngine([("(", "x"), (r"\bdeca\b", "djeca"), ("abc",), ()])
    assert e.broj_patterna == 1
    assert e.primijeni("deca")[0] == "djeca"


def test_whitelist_stiti_kljuc_glosara():
    e = KalkoviEngine([(r"\bsvetlo\b", "svjetlo")])
    assert e.primijeni("Ovo svetlo gori.")[0] == "Ovo svjetlo gori."
    izlaz, n = e.primijeni("Ovo svetlo gori.", glosar={"svetlo": None})
    assert izlaz == "Ovo svetlo gori."
    assert n == 0


def test_whitelist_stiti_hrvatsku_vrijednost_glosara():
    e = KalkoviEngine([(r"\bpetak\b", "petak2")])
    izlaz, n = e.primijeni("U petak.", glosar={"Friday": "petak"})
    assert izlaz == "U petak."
    assert n == 0


def test_whitelist_je_kesiran_po_sadrzaju():
    g1 = {"Friday": "petak"}
    g2 = {"Friday": "petak"}
    assert E._whitelist_za(g1) is E._whitelist_za(g2)
    assert E._whitelist_za({}) is None
    assert E._whitelist_za(None) is None


def test_statistika_po_kategoriji():
    e = KalkoviEngine([(r"\bdeca\b", "djeca", "ekavizmi"), (r"\bko je\b", "tko je", "da")])
    e.primijeni("Deca. Ko je to?")
    s = e.statistike()
    assert s["zamjene_po_kategoriji"] == {"ekavizmi": 1, "da": 1}
    assert s["kategorije"] == {"ekavizmi": 1, "da": 1}
    assert s["ukupno_patterna"] == 2


def test_dinamicki_samo_cijele_rijeci():
    e = KalkoviEngine([("ko", "tko", "dinamicki")])
    assert e.primijeni("Kokoš i ko.")[0] == "Kokoš i tko."


def test_prazan_tekst():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    assert e.primijeni("") == ("", 0)
    assert e.primijeni("   ") == ("   ", 0)


def test_dnevnik_zamjena_se_upisuje(tmp_path, monkeypatch):
    putanja = tmp_path / "zamjene.jsonl"
    monkeypatch.setattr(E, "LOG_PATH", putanja)
    e = KalkoviEngine([(r"\bdeca\b", "djeca", "ekavizmi")])
    e.primijeni("Deca.", blok_id="b1")
    redovi = [json.loads(r) for r in putanja.read_text(encoding="utf-8").splitlines()]
    assert len(redovi) == 1
    assert redovi[0]["blok"] == "b1"
    assert redovi[0]["kat"] == "ekavizmi"
    assert redovi[0]["iz"] == "Deca"
    assert redovi[0]["u"] == "Djeca"


def test_zadani_dnevnik_se_ne_pise_pod_pytestom():
    e = KalkoviEngine([(r"\bdeca\b", "djeca", "ekavizmi")])
    prije = E._ZADANI_DNEVNIK.stat().st_size if E._ZADANI_DNEVNIK.exists() else None
    e.primijeni("Deca.", blok_id="pytest")
    poslije = E._ZADANI_DNEVNIK.stat().st_size if E._ZADANI_DNEVNIK.exists() else None
    assert prije == poslije


def test_html_safe_wrapper_vraca_par():
    izlaz, n = E.primijeni_html_safe("tekst bez zamjena")
    assert isinstance(izlaz, str)
    assert isinstance(n, int)


def test_sve_liste_kat_je_uskladjen_sa_engineom():
    from core import kalkovi as K

    assert len(K.SVE_LISTE_KAT) == len(K.SVE_LISTE)
    assert all(len(e) == 3 and e[2] in K._KATEGORIJE for e in K.SVE_LISTE_KAT)
    assert 0 < E.kalkovi_engine.broj_patterna <= len(K.SVE_LISTE_KAT)


def test_reload_dinamickih_zadrzava_broj_patterna():
    from core import kalkovi as K

    prije = E.kalkovi_engine.broj_patterna
    poslije = K.reload_dinamicki_kalkove()
    assert poslije == prije
    assert E.kalkovi_engine.broj_patterna == prije
