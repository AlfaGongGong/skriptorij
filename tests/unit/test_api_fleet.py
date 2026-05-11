import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api_fleet import FleetManager


def _make_fleet(tmp_path):
    cfg = tmp_path / "dev_api.json"
    state = tmp_path / "api_state.json"
    cfg.write_text(json.dumps({"GROQ": ["gsk_test_1234567890"]}), "utf-8")
    return FleetManager(config_path=str(cfg), state_path=str(state))


def test_toggle_reactivates_auto_disabled_key(tmp_path):
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    ks.is_active = False
    ks.disabled = False
    ks.cooldown_until = time.time() + 120

    result = fm.toggle_key("GROQ", ks.masked)

    assert result["ok"] is True
    assert result["disabled"] is False
    assert ks.disabled is False
    assert ks.is_active is True
    assert ks.cooldown_until == 0.0


def test_toggle_cycle_manual_off_on_still_works(tmp_path):
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    off = fm.toggle_key("GROQ", ks.masked)
    on = fm.toggle_key("GROQ", ks.masked)

    assert off["disabled"] is True
    assert on["disabled"] is False
    assert ks.disabled is False
    assert ks.is_active is True


def test_available_auto_revives_after_cooldown_expiry(tmp_path):
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    ks.is_active = False
    ks.disabled = False
    ks.cooldown_until = time.time() - 5

    assert ks.available is True
    assert ks.is_active is True
    assert ks.cooldown_until == 0.0


def test_rate_limit_errors_do_not_force_inactive_state(tmp_path):
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    for _ in range(3):
        fm.analyze_response(
            "GROQ",
            ks.key,
            429,
            {"retry-after": "30"},
            {"error": {"message": "Rate limit"}},
        )

    assert ks.disabled is False
    assert ks.is_active is True
    assert ks.cooldown_remaining > 0
