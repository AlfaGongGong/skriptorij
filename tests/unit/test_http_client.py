import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network import http_client


def test_google_pool_uses_only_whitelisted_models(monkeypatch):
    monkeypatch.setattr(
        "network.model_discovery.get_cached_model_list",
        lambda _provider: [
            "gemini-3-flash",
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.0-flash",
            "some-random-model",
        ],
    )

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    assert "gemini-3-flash" not in model_ids
    assert "some-random-model" not in model_ids
    assert model_ids[0] == "gemini-2.5-flash-preview-05-20"
    assert "gemini-2.0-flash" in model_ids


def test_google_pool_falls_back_when_discovery_empty(monkeypatch):
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _provider: [])
    pool = http_client._get_google_model_pool()

    assert pool == http_client._GOOGLE_MODEL_POOL_FALLBACK
