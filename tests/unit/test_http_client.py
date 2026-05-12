import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network import http_client
import network.model_discovery as _md


def _reset_dead_models():
    """Pomoćnik: čisti dead_models state između testova."""
    _md.clear_dead_models()


def test_google_pool_uses_only_whitelisted_models(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr(
        "network.model_discovery.get_cached_model_list",
        lambda _provider: [
            "gemini-3-flash",
            "gemini-2.5-flash",       # GA verzija (whitelisted); preview je uklonjen (404)
            "gemini-2.0-flash",
            "some-random-model",
        ],
    )
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: frozenset())

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    # Modeli koji nisu u statičkom fallback whitelistu ostaju van poola
    assert "gemini-3-flash" not in model_ids
    assert "some-random-model" not in model_ids
    # Whitelistirani modeli su prisutni; discovery određuje redosljed
    assert model_ids[0] == "gemini-2.5-flash"
    assert "gemini-2.0-flash" in model_ids


def test_google_pool_falls_back_when_discovery_empty(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _provider: [])
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: frozenset())
    pool = http_client._get_google_model_pool()

    assert pool == http_client._GOOGLE_MODEL_POOL_FALLBACK


def test_google_pool_excludes_dead_models(monkeypatch):
    """Dead modeli (HTTP 404) moraju biti isključeni iz poola."""
    _reset_dead_models()
    dead_model = "gemini-2.5-flash-lite-preview-06-17"
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _p: [])
    monkeypatch.setattr(
        "network.model_discovery.get_dead_models",
        lambda _p: frozenset({dead_model}),
    )

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    assert dead_model not in model_ids
    # Ostali whitelistirani modeli ostaju
    assert "gemini-2.0-flash" in model_ids


def test_google_pool_all_dead_returns_full_fallback(monkeypatch):
    """Kad su SVI modeli dead, mora se vratiti puni fallback (sigurnosna mreža)."""
    _reset_dead_models()
    all_dead = frozenset(m["model"] for m in http_client._GOOGLE_MODEL_POOL_FALLBACK)
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _p: [])
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: all_dead)

    pool = http_client._get_google_model_pool()
    # Ne smijemo vraćati prazan pool (izazvao bi ZeroDivisionError u rotaciji)
    assert len(pool) > 0


def test_mark_model_dead_and_get():
    _reset_dead_models()
    _md.mark_model_dead("GEMINI", "gemini-bad-model")
    dead = _md.get_dead_models("GEMINI")
    assert "gemini-bad-model" in dead


def test_invalidate_cached_model_marks_dead():
    _reset_dead_models()
    # Postavi cache
    _md._set_cached_model_list("GEMINI", ["gemini-2.0-flash", "gemini-2.5-flash-lite-preview-06-17"])

    _md.invalidate_cached_model("GEMINI", "gemini-2.0-flash")

    dead = _md.get_dead_models("GEMINI")
    assert "gemini-2.0-flash" in dead
    # Sljedeći model je promoviran
    cached = _md.get_cached_model("GEMINI")
    assert cached == "gemini-2.5-flash-lite-preview-06-17"


def test_set_cached_model_list_revives_dead_models():
    """Kad API ponovo vrati model koji smo smatrali dead, treba ga oživjeti."""
    _reset_dead_models()
    _md.mark_model_dead("GEMINI", "gemini-2.0-flash")
    assert "gemini-2.0-flash" in _md.get_dead_models("GEMINI")

    # API ponovo vraća model u listi — oživjava ga
    _md._set_cached_model_list("GEMINI", ["gemini-2.0-flash", "gemini-2.5-flash-lite-preview-06-17"])

    assert "gemini-2.0-flash" not in _md.get_dead_models("GEMINI")


def test_build_messages_uses_user_only_for_models_without_system_role():
    msgs = http_client._build_messages("sys", "usr", "gemma-3-27b-it")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert "[INSTRUKCIJE]" in msgs[0]["content"]


def test_build_messages_uses_system_for_supported_models():
    msgs = http_client._build_messages("sys", "usr", "gpt-4o")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
