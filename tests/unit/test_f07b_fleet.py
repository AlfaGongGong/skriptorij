import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api_fleet import FleetManager
from network.quota_tracker import quota_tracker

ROOT = Path(__file__).resolve().parents[2]


def _fleet(tmp_path, kljucevi=("AIzaTESTKEY00000001", "AIzaTESTKEY00000002")):
    cfg = tmp_path / "dev_api.json"
    quota_tracker._providers.clear()
    quota_tracker._PERSIST_PATH = str(tmp_path / "quota_cooldowns.json")
    cfg.write_text(json.dumps({"GEMINI": list(kljucevi)}), "utf-8")
    return FleetManager(config_path=str(cfg), state_path=str(tmp_path / "st.json")), list(kljucevi)


def _dobar():
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]}


def test_koristan_odgovor_broji_se_jednom(tmp_path):
    fm, (k1, _) = _fleet(tmp_path)
    fm.record_request("GEMINI", k1)
    fm.analyze_response("GEMINI", k1, 200, {}, _dobar())
    ks = fm.fleet["GEMINI"][0]
    assert ks.calls_ok == 1 and ks.total_requests == 1


def test_http_sloj_ne_zove_record_success_i_failure_na_429():
    src = (ROOT / "network/http_client.py").read_text(encoding="utf-8")
    assert "self.fleet.record_success" not in src
    m = re.search(r"if resp\.status_code in \(429, 425\):(.*?)register_provider_runtime_limits", src, re.S)
    assert m and "record_failure" not in m.group(1)


def test_record_failure_ne_udvostrucuje_pokusaje(tmp_path):
    fm, (k1, _) = _fleet(tmp_path)
    fm.record_request("GEMINI", k1)
    fm.record_failure("GEMINI", k1)
    ks = fm.fleet["GEMINI"][0]
    assert ks.total_requests == 1 and ks.calls_failed == 1


def test_503_visoka_potraznja_ne_gasi_kljuc(tmp_path):
    fm, (k1, k2) = _fleet(tmp_path, kljucevi=("AIzaTESTKEY00000001",))
    fm.analyze_response("GEMINI", k1, 503, {}, {"error": {"status": "UNAVAILABLE"}})
    assert fm.fleet["GEMINI"][0]._last_503_time == 0.0


def test_503_prava_greska_gasi_kljuc(tmp_path):
    fm, (k1, _) = _fleet(tmp_path, kljucevi=("AIzaTESTKEY00000001",))
    fm.analyze_response("GEMINI", k1, 503, {}, {"error": {"status": "INTERNAL"}})
    assert fm.fleet["GEMINI"][0]._last_503_time > 0


def test_provjera_dostupnosti_ne_pomice_kotac(tmp_path):
    fm, _ = _fleet(tmp_path)
    prije = dict(fm._rr_index)
    assert fm.ima_dostupan_kljuc("GEMINI") is True
    assert fm.ima_dostupan_kljuc("NEMA") is False
    assert fm._rr_index == prije
    fm.get_best_key("GEMINI")
    assert fm._rr_index != prije


def test_router_koristi_provjeru_bez_pomaka():
    src = (ROOT / "network/provider_router.py").read_text(encoding="utf-8")
    assert "ima_dostupan_kljuc" in src
