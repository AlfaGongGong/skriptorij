import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from core import odluke


@pytest.fixture(autouse=True)
def privremeni_fajl(monkeypatch):
    p = Path(__file__).resolve().parent / "_odluke_test.jsonl"
    p.unlink(missing_ok=True)
    monkeypatch.setattr(odluke, "PUTANJA", p)
    yield
    p.unlink(missing_ok=True)


def test_kljuc_ignorira_razmake_i_velika_slova():
    assert odluke.kljuc("A  b", "C d") == odluke.kljuc("a b ", " c D")


def test_ostavi_gasi_karticu():
    assert not odluke.je_odbacen("knife", "nož")
    odluke.zabiljezi("K1", "p1_blok_0", "knife", "nož", "kriv_smisao", "ostavi")
    assert odluke.je_odbacen("knife", "nož")


def test_ponisti_vraca_stanje():
    odluke.zabiljezi("K1", "b", "x", "y", "t", "ostavi")
    odluke.zabiljezi("K1", "b", "x", "y", "t", "ponisti")
    assert not odluke.je_odbacen("x", "y")


def test_automatsko_prevodjenje_tek_nakon_praga():
    odluke.zabiljezi("K1", "b", "croquet", "kriket", "kriv_smisao", "prevedi_ponovo")
    assert not odluke.za_automatsko_prevodjenje("croquet", "kriket")
    odluke.zabiljezi("K2", "b", "croquet", "kriket", "kriv_smisao", "prevedi_ponovo")
    assert odluke.za_automatsko_prevodjenje("croquet", "kriket")


def test_statistika_i_nepoznata_odluka():
    odluke.zabiljezi("K1", "b1", "a", "b", "broj", "prevedi_ponovo")
    odluke.zabiljezi("K1", "b2", "c", "d", "broj", "ostavi")
    assert odluke.statistika()["broj"]["preciznost"] == 0.5
    with pytest.raises(ValueError):
        odluke.zabiljezi("K1", "b", "a", "b", "broj", "nesto")


def test_odlucen_po_knjizi():
    assert not odluke.odlucen("K1", "a", "b")
    odluke.zabiljezi("K1", "b", "a", "b", "broj", "preskoci")
    assert odluke.odlucen("K1", "a", "b")
    assert not odluke.odlucen("K2", "a", "b")
