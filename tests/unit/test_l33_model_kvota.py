"""L33: dnevna kvota po ključu i modelu, trajno pamćenje i ispis."""
import json
import time

from network import quota_tracker as qtm
from network.quota_tracker import (
    QuotaTracker,
    dan_kvote,
    je_dnevni_limit,
    model_iz_url,
    sekundi_do_reseta,
)

KEY = "AIzaSyTESTKEY0001abcd"
M1, M2 = "gemini-3.5-flash", "gemini-3.1-flash-lite"


def _tracker(tmp_path, monkeypatch):
    monkeypatch.setattr(QuotaTracker, "_PERSIST_PATH", str(tmp_path / "qc.json"))
    t = QuotaTracker()
    t.register_key("GEMINI", KEY, min_gap_s=0.0)
    return t


def test_model_iz_url():
    u = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
    assert model_iz_url(u) == "gemini-3.5-flash"
    assert model_iz_url("https://x.y/z") == ""


def test_je_dnevni_limit():
    body = {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
    assert je_dnevni_limit(body)
    assert je_dnevni_limit("You exceeded your daily quota")
    rpm = {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}
    assert not je_dnevni_limit(rpm)


def test_sekundi_do_reseta_raspon():
    s = sekundi_do_reseta()
    assert 60.0 <= s <= 86400.0 + 3700.0
    assert len(dan_kvote()) == 10


def test_model_cooldown_ne_gasi_kljuc(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    assert t.obradi_429_model("GEMINI", KEY, M1, {"error": {"message": "quota per day"}})
    assert t.is_model_available("GEMINI", KEY, M1)[0] is False
    assert t.is_model_available("GEMINI", KEY, M2)[0] is True
    assert t.is_key_available("GEMINI", KEY)[0] is True


def test_rpm_429_nije_dnevni(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    rpm = {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"}]}]}}
    assert not t.obradi_429_model("GEMINI", KEY, M1, rpm)
    assert t.is_model_available("GEMINI", KEY, M1)[0] is True


def test_record_response_model_limit_bez_cooldowna(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    t.record_response("GEMINI", KEY, 429, model=M1, model_limit=True)
    assert t.is_key_available("GEMINI", KEY)[0] is True


def test_trajno_pamcenje_i_restore(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    t.obradi_429_model("GEMINI", KEY, M1, "per day")
    for _ in range(3):
        t.record_model_request("GEMINI", KEY, M2)
    t._persist_cooldowns()
    d = json.loads((tmp_path / "qc.json").read_text())
    assert M1 in d["GEMINI"][KEY]["model_cooldowns"]
    t2 = _tracker(tmp_path, monkeypatch)
    t2._restore_cooldowns()
    assert t2.is_model_available("GEMINI", KEY, M1)[0] is False
    assert t2.is_model_available("GEMINI", KEY, M2)[0] is True
    txt = "\n".join(t2.ispis_stanja())
    assert M1 in txt and "ISCRPLJEN" in txt and "poziva danas" in txt


def test_istekli_se_resetira(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    (tmp_path / "qc.json").write_text(
        json.dumps(
            {
                "GEMINI": {
                    KEY: {
                        "cooldown_until": 0,
                        "cooldown_reason": "",
                        "model_cooldowns": {M1: {"until": time.time() - 5, "reason": "x"}},
                        "model_rpd": {M2: {"dan": "2000-01-01", "n": 99}},
                    }
                }
            }
        )
    )
    t._restore_cooldowns()
    assert t.is_model_available("GEMINI", KEY, M1)[0] is True
    kq = t._get_provider("GEMINI").get_key(KEY)
    assert M2 not in kq._model_rpd
    assert any(M1 in x for x in t._restored_info["istekli"])


def test_brojac_dana_resetira(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    kq = t._get_provider("GEMINI").get_key(KEY)
    kq._model_rpd[M1] = {"dan": "2000-01-01", "n": 50}
    assert kq.record_model_request(M1) == 1


def test_ispis_bez_iscrpljenja(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    txt = "\n".join(t.ispis_stanja())
    assert "resetiraju" in txt and "nijedan" in txt
