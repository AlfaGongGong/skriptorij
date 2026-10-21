"""tests/unit/test_quality_class.py — core.quality_class.classify_quality"""
from core.quality_class import DEFAULT_THRESHOLDS, classify_quality


def _ok_metrics(**izmjene):
    m = {
        "ekavizmi_per_1000": 0.5,
        "en_ostaci_per_1000": 2.0,
        "duplikati": 0,
        "ratio_source_target": 1.05,
        "tipografija_greske": 1,
        "reci_ukupno": 1500,
    }
    m.update(izmjene)
    return m


def test_ok():
    assert classify_quality(_ok_metrics()) == "OK"


def test_review_ekavizmi():
    assert classify_quality(_ok_metrics(ekavizmi_per_1000=2.0)) == "REVIEW"


def test_review_duplikati():
    assert classify_quality(_ok_metrics(duplikati=1)) == "REVIEW"


def test_reject_ekavizmi():
    assert classify_quality(_ok_metrics(ekavizmi_per_1000=5.0)) == "REJECT"


def test_reject_tipografija():
    assert classify_quality(_ok_metrics(tipografija_greske=11)) == "REJECT"


def test_prazan_metrics():
    assert classify_quality({}) == "OK"


def test_ratio_none():
    assert classify_quality(_ok_metrics(ratio_source_target=None)) == "OK"
    assert classify_quality(_ok_metrics(ratio_source_target=None, duplikati=1)) == "REVIEW"
    assert classify_quality(_ok_metrics(ratio_source_target=3.0)) == "REJECT"


def test_custom_thresholds():
    m = _ok_metrics(ekavizmi_per_1000=2.0)
    assert classify_quality(m) == "REVIEW"
    assert classify_quality(m, {"ekavizmi_per_1000_ok": 5.0, "ekavizmi_per_1000_review": 8.0}) == "OK"
    assert classify_quality(m, {"ekavizmi_per_1000_review": 1.5}) == "REJECT"
    assert DEFAULT_THRESHOLDS["ekavizmi_per_1000_ok"] == 1.0
