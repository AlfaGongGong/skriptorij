import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api_fleet import FleetManager
from network.quota_tracker import quota_tracker

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _fleet(tmp_path):
    cfg = tmp_path / "dev_api.json"
    quota_tracker._providers.clear()
    quota_tracker._PERSIST_PATH = str(tmp_path / "quota_cooldowns.json")
    cfg.write_text(json.dumps({"GEMINI": ["AIzaKEY00000001", "AIzaKEY00000002"]}), "utf-8")
    return FleetManager(config_path=str(cfg), state_path=str(tmp_path / "st.json"))


def test_has_available_key_ne_pomice_kotac(tmp_path):
    fm = _fleet(tmp_path)
    prije = dict(fm._rr_index)
    assert fm.has_available_key("GEMINI") is True
    assert fm.has_available_key("GEMINI") is True
    assert fm._rr_index == prije
    assert fm.has_available_key("NEMA") is False


def test_kotac_ide_jednom_po_odabiru(tmp_path):
    fm = _fleet(tmp_path)
    k1 = fm.get_best_key("GEMINI")
    k2 = fm.get_best_key("GEMINI")
    assert k1 != k2


def test_503_hladan_nije_dostupan(tmp_path):
    import time
    fm = _fleet(tmp_path)
    for ks in fm.fleet["GEMINI"]:
        ks._last_503_time = time.time()
    assert fm.has_available_key("GEMINI") is False


def test_record_failure_ne_dira_total_requests(tmp_path):
    fm = _fleet(tmp_path)
    key = fm.fleet["GEMINI"][0].key
    fm.record_request("GEMINI", key)
    fm.record_failure("GEMINI", key)
    ks = fm.fleet["GEMINI"][0]
    assert ks.total_requests == 1 and ks.calls_failed == 1


def test_200_se_broji_jednom(tmp_path):
    fm = _fleet(tmp_path)
    key = fm.fleet["GEMINI"][0].key
    body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "x"}]}}]}
    fm.analyze_response("GEMINI", key, 200, {}, body)
    assert fm.fleet["GEMINI"][0].calls_ok == 1


def test_http_client_bez_dupliranja():
    src = open(os.path.join(ROOT, "network", "http_client.py"), encoding="utf-8").read()
    assert "fleet.record_success(" not in src
    i = src.index("if resp.status_code in (429, 425):")
    assert "record_failure" not in src[i:i + 200]


def test_router_koristi_has_available_key():
    src = open(os.path.join(ROOT, "network", "provider_router.py"), encoding="utf-8").read()
    assert len(re.findall(r"self\.fleet\.has_available_key\(prov_upper\)", src)) == 2
    assert "fleet.has_available_key(prov_u)" in src
