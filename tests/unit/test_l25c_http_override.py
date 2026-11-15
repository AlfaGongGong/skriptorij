import os

from network import http_client as hc


def test_override_modeli_prazno_bez_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("BOOKLYFI_MODEL_"):
            monkeypatch.delenv(k, raising=False)
    assert hc._l25_override_modeli() == set()


def test_override_modeli_sadrzi_trazeni(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_MODEL_PREVODILAC", "gemini-3.5-flash")
    assert "gemini-3.5-flash" in hc._l25_override_modeli()
