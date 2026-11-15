"""L30: dnevna kvota iscrpljena -> knjiga se zaustavlja umjesto markera po svakom bloku."""
from pathlib import Path

from network.quota_tracker import QuotaTracker

ROOT = Path(__file__).resolve().parents[2]


def _kq(qt, prov, key, cooldown_s=0.0):
    qt.register_key(prov, key)
    kq = qt._providers[prov.upper()].get_key(key)
    if cooldown_s:
        kq.set_cooldown_external(cooldown_s, "RPD kvota (dnevni limit)")
    return kq


def test_bez_kljuceva_nije_iscrpljeno():
    assert QuotaTracker().dnevna_kvota_iscrpljena() == (False, 0.0)


def test_svi_kljucevi_dnevni_cooldown():
    qt = QuotaTracker()
    _kq(qt, "GEMINI", "k1", 7200)
    _kq(qt, "GROQ", "k2", 5000)
    iscr, rem = qt.dnevna_kvota_iscrpljena()
    assert iscr is True
    assert 4900 < rem <= 5000


def test_jedan_slobodan_kljuc_nije_iscrpljeno():
    qt = QuotaTracker()
    _kq(qt, "GEMINI", "k1", 7200)
    _kq(qt, "GROQ", "k2", 0)
    assert qt.dnevna_kvota_iscrpljena() == (False, 0.0)


def test_kratki_cooldown_nije_dnevni():
    qt = QuotaTracker()
    _kq(qt, "GEMINI", "k1", 600)
    assert qt.dnevna_kvota_iscrpljena() == (False, 0.0)


def test_integracija_u_kodu():
    pipe = (ROOT / "processing/pipeline.py").read_text("utf-8")
    par = (ROOT / "processing/parallel.py").read_text("utf-8")
    wrk = (ROOT / "processing/workers.py").read_text("utf-8")
    assert "dnevna_kvota_iscrpljena(" in pipe and 'return None, "QUOTA_STOP"' in pipe
    assert pipe.index("dnevna_kvota_iscrpljena(") < pipe.index("[[NEPREVEDENO: chunk")
    assert 'getattr(self.engine, "kvota_stop", False)' in par
    assert 'if eng == "QUOTA_STOP":' in par
    assert wrk.index('_e == "QUOTA_STOP"') < wrk.index("final_parts = []")
