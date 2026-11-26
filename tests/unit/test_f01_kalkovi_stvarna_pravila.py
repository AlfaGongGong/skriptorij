"""F01a: stvarna pravila kroz stvarni engine (primjeri iz audita R11a-3/R11a-22)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.kalkovi import engine as E  # noqa: E402


@pytest.fixture(autouse=True)
def _bez_dnevnika(monkeypatch):
    monkeypatch.setattr(E, "LOG_PATH", None)


@pytest.mark.parametrize(
    "ulaz,ocekivano",
    [
        ("Deca su došla.", "Djeca su došla."),
        ("Ceo dan je radio.", "Cijeli dan je radio."),
        ("Ko je to?", "Tko je to?"),
        ("<p>Ceo dan.</p>", "<p>Cijeli dan.</p>"),
    ],
)
def test_stvarna_pravila(ulaz, ocekivano):
    assert E.kalkovi_engine.primijeni(ulaz)[0] == ocekivano


def test_engine_ima_dovoljno_patterna():
    assert E.kalkovi_engine.broj_patterna > 100
