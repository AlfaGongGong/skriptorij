"""L34: iscrpljenost po modelu (L33) mora zaustaviti knjigu; stari cooldown ključa se ne vraća s diska."""
import json
import time

from config.ai_config import GOOGLE_MODEL_POOL
from network.quota_tracker import QuotaTracker

KEY = "AIzaSyTESTKEY0001abcd"
MODELI = [m["model"] for m in GOOGLE_MODEL_POOL]


def _t(tmp_path, monkeypatch):
    monkeypatch.setattr(QuotaTracker, "_PERSIST_PATH", str(tmp_path / "qc.json"))
    t = QuotaTracker()
    t.register_key("GEMINI", KEY, min_gap_s=0.0)
    return t


def _kq(t):
    return t._providers["GEMINI"].get_key(KEY)


def test_svi_modeli_pool_u_limitu_je_iscrpljeno(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    for m in MODELI:
        _kq(t).set_model_cooldown(m, 7200, "dnevni limit modela")
    iscr, rem = t.dnevna_kvota_iscrpljena(provs=["GEMINI"])
    assert iscr is True and 7000 < rem <= 7200


def test_jedan_model_slobodan_nije_iscrpljeno(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    _kq(t).set_model_cooldown(MODELI[0], 7200, "dnevni limit modela")
    assert t.dnevna_kvota_iscrpljena(provs=["GEMINI"]) == (False, 0.0)


def test_strogi_provider_ignorira_druge(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    t.register_key("GROQ", "gsk_free", min_gap_s=0.0)
    for m in MODELI:
        _kq(t).set_model_cooldown(m, 7200, "dnevni limit modela")
    assert t.dnevna_kvota_iscrpljena(provs=["GEMINI"])[0] is True
    assert t.dnevna_kvota_iscrpljena() == (False, 0.0)


def test_kljuc_cooldown_i_dalje_radi(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    _kq(t).set_cooldown_external(7200, "RPD kvota (dnevni limit)")
    assert t.dnevna_kvota_iscrpljena(provs=["GEMINI"])[0] is True


def test_stari_cooldown_kljuca_se_ne_vraca(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    p = tmp_path / "qc.json"
    p.write_text(json.dumps({"GEMINI": {KEY: {
        "cooldown_until": time.time() + 7200, "cooldown_reason": "RPD kvota (dnevni limit)"}}}), encoding="utf-8")
    t._restore_cooldowns()
    assert _kq(t).cooldown_remaining() == 0.0
    assert any("stari cooldown" in x for x in t._restored_info["istekli"])


def test_modelski_cooldown_se_i_dalje_vraca(tmp_path, monkeypatch):
    t = _t(tmp_path, monkeypatch)
    t.obradi_429_model("GEMINI", KEY, MODELI[0], "per day")
    t2 = QuotaTracker()
    t2.register_key("GEMINI", KEY, min_gap_s=0.0)
    t2._restore_cooldowns()
    assert t2.is_model_available("GEMINI", KEY, MODELI[0])[0] is False
