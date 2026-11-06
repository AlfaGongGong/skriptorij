import importlib.util
import pathlib

import pytest


def _audit():
    p = pathlib.Path(__file__).resolve().parents[2] / "tools" / "audit_epub.py"
    spec = importlib.util.spec_from_file_location("audit_epub_t", p)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception as e:
        pytest.skip("audit_epub se ne moze uvesti: %s" % e)
    return m


def test_navod_nastavlja_u_sljedecem_pasusu():
    a = _audit()
    t = "„Koji su im sve uništili. Trebamo vojsku."
    assert a._navod_nastavak(t, {"_prev": "", "_next": "Moramo dobiti konce.”"}, 1, 0)


def test_navod_nastavak_prethodnog_pasusa():
    a = _audit()
    t = "Moramo dobiti konce.”"
    assert a._navod_nastavak(t, {"_prev": "„Koji su im sve uništili.", "_next": ""}, 0, 1)


def test_stvarna_greska_nije_nastavak():
    a = _audit()
    t = "„Ovčetina, izustila je hvatajući zrak."
    assert not a._navod_nastavak(t, {"_prev": "Neki tekst.", "_next": "Drugi pasus."}, 1, 0)
