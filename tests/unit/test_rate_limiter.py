import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network import rate_limiter


def test_register_provider_backoff_keeps_longest_deadline(monkeypatch):
    monkeypatch.setattr("network.rate_limiter.time.time", lambda: 100.0)
    rate_limiter._PROVIDER_COOLDOWN_UNTIL.clear()

    rate_limiter.register_provider_backoff("gemini", 10)
    first = rate_limiter._PROVIDER_COOLDOWN_UNTIL["GEMINI"]
    assert first == 110.0

    # Kraći backoff ne smije skratiti postojeći rok
    rate_limiter.register_provider_backoff("GEMINI", 5)
    assert rate_limiter._PROVIDER_COOLDOWN_UNTIL["GEMINI"] == 110.0

    # Duži backoff mora produžiti rok
    rate_limiter.register_provider_backoff("GEMINI", 20)
    assert rate_limiter._PROVIDER_COOLDOWN_UNTIL["GEMINI"] == 120.0
