import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.ai_config import MODEL_MAP
from network.provider_router import _resolve_model_generation_params


def test_resolve_model_generation_params_applies_exact_model_override():
    temp, max_tokens = _resolve_model_generation_params(
        "PREVODILAC",
        "gemini-2.0-flash",
        0.5,
        2800,
    )
    assert round(temp, 3) == round(0.5 * 0.88, 3)
    assert max_tokens == 2200


def test_resolve_model_generation_params_applies_family_fallback():
    temp, max_tokens = _resolve_model_generation_params(
        "LEKTOR",
        "some-unknown-gemini-model",
        0.45,
        2800,
    )
    assert round(temp, 3) == round(0.45 * 0.90, 3)
    assert max_tokens == 2200


def test_call_ai_engine_uses_gemma_cooldown_namespace_for_gemma_provider(monkeypatch):
    class FakeQuotaTracker:
        def __init__(self):
            self.providers = []

        def is_key_available(self, provider, key):
            self.providers.append(provider)
            if provider == "GEMMA":
                return True, ""
            return False, "cooldown 120s (RPM 429)"

    fake_quota_tracker = FakeQuotaTracker()
    monkeypatch.setattr("network.quota_tracker.quota_tracker", fake_quota_tracker)

    async def fake_call_single_provider(self_obj, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=2400):
        if prov_upper == "GEMMA":
            return "OK", f"{prov_upper}-{model}"
        return None, None

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("network.provider_router._call_single_provider", fake_call_single_provider)
    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    class FakeFleet:
        def __init__(self):
            key_state = type("KeyState", (), {"key": "KEY_1234", "success_rate": 1.0})()
            self.fleet = {"GEMINI": [key_state], "GEMMA": [key_state]}

        def get_active_model(self, provider):
            return MODEL_MAP[provider]

    class FakeEngine:
        def __init__(self):
            self.fleet = FakeFleet()
            self.shared_controls = {}

        def log(self, msg, level="info"):
            pass

    content, label = asyncio.run(
        __import__("network.provider_router", fromlist=["_call_ai_engine"])._call_ai_engine(
            FakeEngine(),
            "prompt",
            0,
            uloga="GUARDIAN",
            sys_override="sys",
        )
    )

    assert content == "OK"
    assert label == f"GEMMA-{MODEL_MAP['GEMMA']}"
    assert fake_quota_tracker.providers[:2] == ["GEMINI", "GEMMA"]
