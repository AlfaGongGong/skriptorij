"""F01b: whitelist, statistika, dnevnik zamjena, promoter (R11a-11/18/22/23, R11b-4)."""
import json
import sqlite3
import threading

import pytest

import core.kalkovi as K
from core.kalkovi import dinamicki_promoter as prom
from core.kalkovi import engine as eng
from core.kalkovi import kalkovi_da
from core.kalkovi.engine import KalkoviEngine, kalkovi_engine


@pytest.fixture(autouse=True)
def _bez_dnevnika(monkeypatch):
    monkeypatch.setattr(eng, "LOG_PATH", None)


def test_r11a_11_whitelist_stiti_hr_vrijednosti_i_kesira():
    e = KalkoviEngine([(r"\bceo dan\b", "cijeli dan")])
    assert e.primijeni("Ceo dan")[1] == 1
    glosar = {"The Whole Day": "Ceo dan"}
    assert e.primijeni("Ceo dan", glosar=glosar) == ("Ceo dan", 0)
    assert eng._whitelist_za(glosar) is eng._whitelist_za(dict(glosar))
    assert eng._whitelist_za({}) is None
    assert eng._whitelist_za({"a": None, "b": 3}) is not None


def test_r11a_18_statistika_po_modulu():
    e = KalkoviEngine([(r"\bdeca\b", "djeca", "ekavizmi"), (r"\bceo\b", "cijeli", "dijalog")])
    e.primijeni("deca i deca i ceo")
    assert e.statistike()["zamjene_po_kategoriji"] == {"ekavizmi": 2, "dijalog": 1}
    assert len(K.SVE_LISTE_KAT) == len(K.SVE_LISTE)
    assert {x[2] for x in K.SVE_LISTE_KAT} <= set(K._KATEGORIJE)


def test_r11a_18_reload_usred_obrade_nikad_prazan():
    e = KalkoviEngine([(r"\bdeca\b", "djeca")])
    stop, prazno = threading.Event(), []

    def radi():
        while not stop.is_set():
            e.reload([(r"\bdeca\b", "djeca"), (r"\bceo\b", "cijeli")])

    t = threading.Thread(target=radi)
    t.start()
    try:
        for _ in range(300):
            if e.primijeni("deca")[1] != 1:
                prazno.append(1)
    finally:
        stop.set()
        t.join()
    assert prazno == []


def test_r11a_1_reload_stvarni_engine_stabilan():
    n = K.reload_dinamicki_kalkove()
    assert n == kalkovi_engine.broj_patterna and n >= 500
    assert K.reload_dinamicki_kalkove() == n
    assert kalkovi_engine.primijeni("Deca su došla.")[0] == "Djeca su došla."


def test_r11a_23_dnevnik_zamjena(monkeypatch, tmp_path):
    log = tmp_path / "k.jsonl"
    monkeypatch.setattr(eng, "LOG_PATH", log)
    e = KalkoviEngine([(r"\bdjeca\b", "djeca"), (r"\bdeca\b", "djeca", "ekavizmi")])
    e.primijeni("Deca i djeca", blok_id="blok_7")
    redovi = [json.loads(x) for x in log.read_text("utf-8").splitlines()]
    assert len(redovi) == 1
    r = redovi[0]
    assert r["blok"] == "blok_7" and r["iz"] == "Deca" and r["u"] == "Djeca" and r["kat"] == "ekavizmi"


def test_r11a_23_zadani_dnevnik_se_ne_pise_pod_pytestom(monkeypatch):
    monkeypatch.setattr(eng, "LOG_PATH", eng._ZADANI_DNEVNIK)
    pocetak = eng._ZADANI_DNEVNIK.stat().st_size if eng._ZADANI_DNEVNIK.exists() else 0
    KalkoviEngine([(r"\bdeca\b", "djeca")]).primijeni("deca")
    assert (eng._ZADANI_DNEVNIK.stat().st_size if eng._ZADANI_DNEVNIK.exists() else 0) == pocetak


def test_r11a_22_nema_praznih_unosa():
    assert all(isinstance(e, tuple) and len(e) >= 2 for e in kalkovi_da.KALKOVI)


def _baza(tmp_path, pattern):
    db = tmp_path / "k.db"
    with sqlite3.connect(db) as c:
        c.execute(
            "CREATE TABLE kandidati (id INTEGER PRIMARY KEY, pattern TEXT, tip TEXT, "
            "broj_pojavljivanja INT, ukupan_score REAL, knjige_set TEXT, rollback_count INT, "
            "status TEXT, validator_napomena TEXT, datum_zadnjeg TEXT)"
        )
        c.execute(
            "INSERT INTO kandidati (pattern,tip,broj_pojavljivanja,ukupan_score,knjige_set,"
            "rollback_count,status) VALUES (?,?,?,?,?,?,?)",
            (pattern, "kalk", 10, 75.0, "a,b,c", 0, "potvrden"),
        )
    return db


def test_r11b_4_promoter_ne_pise_praznu_zamjenu(monkeypatch, tmp_path):
    lista = tmp_path / "dinamicki_lista.py"
    sadrzaj = 'DINAMICKI_KALKOVI = [\n    ("hiljada", "tisuća"),\n]\n'
    lista.write_text(sadrzaj, encoding="utf-8")
    monkeypatch.setattr(prom, "DINAMICKI_LISTA_PATH", lista)
    p = prom.DinamickiPromoter(db_path=_baza(tmp_path, "nesto novo"))
    rez = p.promoviraj(dry_run=False)
    assert rez["promoviran"] == []
    assert "nesto novo" in rez["preskocan"]
    assert lista.read_text("utf-8") == sadrzaj
    assert p._generisi_python_unos("x", "kalk") == ""
    assert "djeca" in p._generisi_python_unos("deca", "kalk", "djeca")


def test_r11b_4_preskakanje_i_rollback_po_tocnom_patternu(monkeypatch, tmp_path):
    lista = tmp_path / "dinamicki_lista.py"
    lista.write_text(
        'DINAMICKI_KALKOVI = [\n    ("dete", "dijete"),\n    ("deteta", "djeteta"),\n]\n', encoding="utf-8"
    )
    monkeypatch.setattr(prom, "DINAMICKI_LISTA_PATH", lista)
    p = prom.DinamickiPromoter(db_path=_baza(tmp_path, "dete"))
    assert p._ucitaj_dinamicki_listu() == ['    ("dete", "dijete"),', '    ("deteta", "djeteta"),']
    assert prom._unos_ima_pattern('    ("deteta", "x"),', "dete") is False
    p.rollback_pattern("dete", "test")
    t = lista.read_text("utf-8")
    assert '"deteta"' in t and '("dete",' not in t
