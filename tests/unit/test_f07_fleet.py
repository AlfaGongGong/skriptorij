import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import api_fleet
from api_fleet import FleetManager
from network.quota_tracker import quota_tracker


def _fleet(tmp_path, provider="GEMINI", key="AIzaTESTKEY00000001"):
    cfg = tmp_path / "dev_api.json"
    quota_tracker._providers.clear()
    quota_tracker._PERSIST_PATH = str(tmp_path / "quota_cooldowns.json")
    cfg.write_text(json.dumps({provider: [key]}), "utf-8")
    fm = FleetManager(config_path=str(cfg), state_path=str(tmp_path / "st.json"))
    return fm, cfg, key


def _tijelo(finish):
    return {"candidates": [{"finishReason": finish, "content": {"parts": []}}]}


def test_sadrzajni_blok_ne_kaznjava_kljuc(tmp_path, monkeypatch):
    fm, _, key = _fleet(tmp_path)
    poz = []
    monkeypatch.setattr(quota_tracker, "set_key_cooldown", lambda *a, **k: poz.append(a))
    fm.analyze_response("GEMINI", key, 200, {}, _tijelo("PROHIBITED_CONTENT"))
    fm.analyze_response("GEMINI", key, 200, {}, _tijelo("SAFETY"))
    ks = fm.fleet["GEMINI"][0]
    assert poz == [] and ks.calls_failed == 0


def test_prazan_odgovor_i_dalje_kaznjava(tmp_path, monkeypatch):
    fm, _, key = _fleet(tmp_path)
    poz = []
    monkeypatch.setattr(quota_tracker, "set_key_cooldown", lambda *a, **k: poz.append(a))
    fm.analyze_response("GEMINI", key, 200, {}, {"candidates": []})
    assert len(poz) == 1 and fm.fleet["GEMINI"][0].calls_failed == 1


def _uhvati(monkeypatch):
    cap = {}
    monkeypatch.setattr(quota_tracker, "record_response", lambda **k: cap.update(k))
    return cap


def test_retrydelay_iznad_sat_bez_rpd_je_60s(tmp_path, monkeypatch):
    fm, _, key = _fleet(tmp_path)
    cap = _uhvati(monkeypatch)
    tijelo = {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED",
                        "details": [{"retryDelay": "36564s"}]}}
    fm.analyze_response("GEMINI", key, 429, {}, tijelo)
    assert cap["retry_after"] == 60.0


def test_dnevni_limit_iz_quotaid_u_detaljima(tmp_path, monkeypatch):
    fm, _, key = _fleet(tmp_path)
    cap = _uhvati(monkeypatch)
    tijelo = {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED",
                        "details": [{"violations": [
                            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
    fm.analyze_response("GEMINI", key, 429, {}, tijelo)
    assert cap["retry_after"] > 61.0


def test_ponoc_pacifika_u_rasponu():
    s = api_fleet._sekunde_do_ponoci_pacifika()
    assert 60.0 < s <= 90000.0


def test_503_se_biljezi_i_filtrira_kljuc(tmp_path):
    fm, _, key = _fleet(tmp_path)
    fm.analyze_response("GEMINI", key, 503, {}, None)
    assert fm.fleet["GEMINI"][0]._last_503_time > 0
    assert fm.get_best_key("GEMINI") is None


def test_reload_s_neispravnim_jsonom_zadrzava_flotu(tmp_path):
    fm, cfg, key = _fleet(tmp_path)
    cfg.write_text("{ ovo nije json", "utf-8")
    fm.reload()
    assert [k.key for k in fm.fleet["GEMINI"]] == [key]


def test_atexit_flush_postoji():
    assert callable(FleetManager._flush_pri_izlazu)
