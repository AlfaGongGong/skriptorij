import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api_fleet import (
    FleetManager, _is_quota_exhausted_body, _is_billing_exhausted_body,
    _DEFAULT_DAILY_QUOTA,
)


def _make_fleet(tmp_path, provider="GROQ", key="gsk_test_1234567890"):
    cfg = tmp_path / "dev_api.json"
    state = tmp_path / "api_state.json"
    cfg.write_text(json.dumps({provider: [key]}), "utf-8")
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


# ── GEMINI-specific billing body check ──────────────────────────────────────

def test_gemini_rpm_429_body_not_classified_as_daily_quota(tmp_path):
    """Google sends 'quota' and 'resource exhausted' even for RPM 429 —
    _is_billing_exhausted_body must NOT match these for Gemini."""
    # Typical Gemini RPM 429 bodies
    rpm_bodies = [
        {"error": {"code": 429, "message": "You are sending too many requests. Please wait before sending more.", "status": "RESOURCE_EXHAUSTED"}},
        {"error": {"message": "Resource has been exhausted (e.g. check quota)."}},
        {"error": {"message": "RESOURCE_EXHAUSTED", "status": "RESOURCE_EXHAUSTED"}},
        "quota exceeded for per-minute-request",
    ]
    for body in rpm_bodies:
        assert _is_billing_exhausted_body(body) is False, f"False positive for: {body}"


def test_gemini_daily_quota_body_IS_classified_correctly(tmp_path):
    """Bodies with billing/account keywords must still trigger long cooldown."""
    billing_bodies = [
        {"error": {"message": "You exceeded your current quota, please check your plan and billing details."}},
        {"error": {"message": "Billing account suspended."}},
        "your current quota has been reached",
        "monthly limit exceeded",
        "out of credits",
    ]
    for body in billing_bodies:
        assert _is_billing_exhausted_body(body) is True, f"False negative for: {body}"


def test_gemini_rpm_429_gets_short_cooldown(tmp_path):
    """Gemini 429 with RPM body (no billing keyword) must get short cooldown, not 23h."""
    fm = _make_fleet(tmp_path, provider="GEMINI", key="AIzatest1234567890")
    ks = fm.fleet["GEMINI"][0]

    # Typical Gemini RPM 429 body
    body = {"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).", "status": "RESOURCE_EXHAUSTED"}}
    fm.analyze_response("GEMINI", ks.key, 429, {"retry-after": "60"}, body)

    # Must NOT get a 23-hour cooldown
    assert ks.cooldown_remaining < 7200, f"Expected short cooldown, got {ks.cooldown_remaining:.0f}s"
    # Must still be active (short cooldown, not disabled)
    assert ks.is_active is True


def test_gemini_billing_429_gets_long_cooldown(tmp_path):
    """Gemini 429 with billing body must get long cooldown."""
    fm = _make_fleet(tmp_path, provider="GEMINI", key="AIzatest1234567890")
    ks = fm.fleet["GEMINI"][0]

    body = {"error": {"message": "You exceeded your current quota, please check your plan and billing details."}}
    fm.analyze_response("GEMINI", ks.key, 429, {}, body)

    # Must get a long cooldown (>= 1 hour)
    assert ks.cooldown_remaining >= 3600, f"Expected long cooldown, got {ks.cooldown_remaining:.0f}s"
    assert ks.is_active is False


# ── req_rem = 0 auto-revive fix ──────────────────────────────────────────────

def test_auto_revive_resets_req_rem_zero(tmp_path):
    """After daily quota 429 (req_rem=0), key must become available again
    once cooldown has expired (auto-revive must reset req_rem)."""
    fm = _make_fleet(tmp_path, provider="GEMINI", key="AIzatest1234567890")
    ks = fm.fleet["GEMINI"][0]

    # Simulate a daily quota 429 that set req_rem = 0 and is_active = False
    ks.is_active = False
    ks.req_rem = 0
    ks.remaining_day = 0
    ks.cooldown_until = time.time() - 5  # cooldown already expired

    # available must trigger auto-revive and reset req_rem
    assert ks.available is True
    assert ks.req_rem > 0
    assert ks.remaining_day > 0
    assert ks.is_active is True


def test_get_best_key_auto_revive_resets_req_rem(tmp_path):
    """get_best_key should also reset req_rem on auto-revive."""
    fm = _make_fleet(tmp_path, provider="GEMINI", key="AIzatest1234567890")
    ks = fm.fleet["GEMINI"][0]

    ks.is_active = False
    ks.req_rem = 0
    ks.remaining_day = 0
    ks.cooldown_until = time.time() - 5

    key = fm.get_best_key("GEMINI")
    assert key is not None
    assert ks.req_rem > 0


def test_toggle_reactivate_resets_req_rem(tmp_path):
    """toggle_key re-enable must reset req_rem if it is 0."""
    fm = _make_fleet(tmp_path, provider="GEMINI", key="AIzatest1234567890")
    ks = fm.fleet["GEMINI"][0]

    ks.is_active = False
    ks.disabled = True
    ks.req_rem = 0
    ks.remaining_day = 0

    result = fm.toggle_key("GEMINI", ks.masked)
    assert result["disabled"] is False
    assert ks.req_rem > 0
