import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api_fleet import FleetManager


def _make_fleet(tmp_path, provider="GROQ", key="gsk_test_1234567890"):
    cfg = tmp_path / "dev_api.json"
    state = tmp_path / "api_state.json"
    cfg.write_text(json.dumps({provider: [key]}), "utf-8")
    return FleetManager(config_path=str(cfg), state_path=str(state))


def test_available_always_true(tmp_path):
    """Ključ je uvijek dostupan — nema hlađenja ni isključivanja."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    assert ks.available is True


def test_get_best_key_returns_key(tmp_path):
    """get_best_key mora uvijek vratiti ključ ako postoji."""
    fm = _make_fleet(tmp_path)
    key = fm.get_best_key("GROQ")
    assert key is not None


def test_calls_ok_increments_on_200(tmp_path):
    """analyze_response za 200 mora inkrementovati calls_ok."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    before = ks.calls_ok

    fm.analyze_response("GROQ", ks.key, 200, {}, None)

    assert ks.calls_ok == before + 1


def test_calls_rejected_increments_on_429(tmp_path):
    """analyze_response za 429 mora inkrementovati calls_rejected[429].
    QuotaTracker primjenjuje cooldown na 429, pa je ključ privremeno nedostupan."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    fm.analyze_response("GROQ", ks.key, 429, {}, None)

    assert ks.calls_rejected.get(429, 0) == 1
    # QuotaTracker primjenjuje cooldown nakon 429 — ključ je privremeno nedostupan
    assert ks.available is False


def test_calls_rejected_increments_on_401(tmp_path):
    """analyze_response za 401 mora biti u calls_rejected[401].
    QuotaTracker primjenjuje cooldown na 401 (1h), pa je ključ privremeno nedostupan."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    fm.analyze_response("GROQ", ks.key, 401, {}, None)

    assert ks.calls_rejected.get(401, 0) == 1
    # QuotaTracker primjenjuje 1h cooldown nakon 401 — ključ je privremeno nedostupan
    assert ks.available is False


def test_calls_failed_increments_on_500(tmp_path):
    """analyze_response za 500 mora inkrementovati calls_failed."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    fm.analyze_response("GROQ", ks.key, 500, {}, None)

    assert ks.calls_failed == 1


def test_record_network_failure(tmp_path):
    """record_network_failure mora inkrementovati calls_failed."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    before = ks.calls_failed

    fm.record_network_failure("GROQ", ks.key)

    assert ks.calls_failed == before + 1


def test_success_rate_new_key_is_one(tmp_path):
    """Novi ključ (sve 0) mora imati success_rate == 1.0."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    assert ks.success_rate == 1.0


def test_success_rate_after_calls(tmp_path):
    """success_rate = calls_ok / ukupno."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    ks.calls_ok = 8
    ks.calls_failed = 1
    ks.calls_rejected = {429: 1}

    assert abs(ks.success_rate - 0.8) < 0.001


def test_record_request_updates_total(tmp_path):
    """record_request mora povećati total_requests."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    before = ks.total_requests

    fm.record_request("GROQ", ks.key)

    assert ks.total_requests == before + 1


def test_to_dict_has_call_counters(tmp_path):
    """to_dict mora sadržavati calls_ok, calls_failed, calls_rejected."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    ks.calls_ok = 5
    ks.calls_failed = 2
    ks.calls_rejected = {429: 1}

    d = ks.to_dict()
    assert d["calls_ok"] == 5
    assert d["calls_failed"] == 2
    assert d["calls_rejected"] == {"429": 1}


def test_to_ui_dict_has_call_counters(tmp_path):
    """to_ui_dict mora sadržavati calls_ok, calls_failed, calls_rejected."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]
    ks.calls_ok = 3
    ks.calls_failed = 1
    ks.calls_rejected = {401: 1}

    ui = ks.to_ui_dict()
    assert ui["calls_ok"] == 3
    assert ui["calls_failed"] == 1
    assert "401" in ui["calls_rejected"]


def test_get_fleet_summary_has_no_cooling(tmp_path):
    """get_fleet_summary ne smije imati 'cooling' ključ."""
    fm = _make_fleet(tmp_path)
    summary = fm.get_fleet_summary()
    for prov_data in summary.values():
        assert "cooling" not in prov_data


def test_get_fleet_ui_has_no_active(tmp_path):
    """get_fleet_ui ne smije imati 'active' ključ (nema hlađenja)."""
    fm = _make_fleet(tmp_path)
    ui = fm.get_fleet_ui()
    for prov_data in ui.values():
        assert "active" not in prov_data


def test_multiple_analyze_responses(tmp_path):
    """Višestruki pozivi ažuriraju sve brojače ispravno."""
    fm = _make_fleet(tmp_path)
    ks = fm.fleet["GROQ"][0]

    fm.analyze_response("GROQ", ks.key, 200, {}, None)
    fm.analyze_response("GROQ", ks.key, 200, {}, None)
    fm.analyze_response("GROQ", ks.key, 429, {}, None)
    fm.analyze_response("GROQ", ks.key, 401, {}, None)

    assert ks.calls_ok == 2
    assert ks.calls_rejected.get(429, 0) == 1
    assert ks.calls_rejected.get(401, 0) == 1
    # QuotaTracker primjenjuje cooldown nakon 429/401 — ključ je privremeno nedostupan
    assert ks.available is False
