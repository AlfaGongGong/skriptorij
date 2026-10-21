"""
core/quality_class.py — kategoricka ocjena bloka iz deterministickih metrika.

classify_quality(metrics) -> "OK" | "REVIEW" | "REJECT"

Cista funkcija: bez AI poziva, bez I/O. Ulaz je dict iz core.metrics.compute_metrics.
`reci_ukupno` se ne koristi za klasifikaciju.
"""

DEFAULT_THRESHOLDS = {
    "ekavizmi_per_1000_ok": 1.0,
    "ekavizmi_per_1000_review": 3.0,
    "en_ostaci_per_1000_ok": 5.0,
    "en_ostaci_per_1000_review": 20.0,
    "duplikati_ok": 0,
    "duplikati_review": 2,
    "tipografija_ok": 3,
    "tipografija_review": 10,
    "ratio_ok_min": 0.8,
    "ratio_ok_max": 1.2,
    "ratio_review_min": 0.5,
    "ratio_review_max": 2.0,
}

_GORNJE = (
    ("ekavizmi_per_1000", "ekavizmi_per_1000"),
    ("en_ostaci_per_1000", "en_ostaci_per_1000"),
    ("duplikati", "duplikati"),
    ("tipografija_greske", "tipografija"),
)

_OK, _REVIEW, _REJECT = 0, 1, 2
_NAZIVI = {_OK: "OK", _REVIEW: "REVIEW", _REJECT: "REJECT"}


def _broj(vrijednost) -> float:
    """Nedostajuce ili neispravne vrijednosti se tretiraju kao 0."""
    if vrijednost is None or isinstance(vrijednost, bool):
        return 0.0
    try:
        return float(vrijednost)
    except (TypeError, ValueError):
        return 0.0


def classify_quality(metrics: dict, thresholds: dict | None = None) -> str:
    """
    Vraca "OK" | "REVIEW" | "REJECT".

    - sve metrike u "ok" granicama      -> OK
    - bilo koja u "review" granicama    -> REVIEW
    - bilo koja van "review" granica    -> REJECT
    - nedostajuci kljucevi = 0; ratio_source_target None/nedostaje -> ratio se preskace
    - `thresholds` (opciono) se spaja preko DEFAULT_THRESHOLDS (parcijalni dict je ok)
    """
    m = metrics if isinstance(metrics, dict) else {}
    t = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        t.update(thresholds)

    nivo = _OK

    for kljuc, prefiks in _GORNJE:
        v = _broj(m.get(kljuc))
        if v <= t[prefiks + "_ok"]:
            continue
        if v <= t[prefiks + "_review"]:
            nivo = max(nivo, _REVIEW)
        else:
            nivo = _REJECT

    ratio = m.get("ratio_source_target")
    if ratio is not None and not isinstance(ratio, bool):
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            r = None
        if r is not None:
            if t["ratio_ok_min"] <= r <= t["ratio_ok_max"]:
                pass
            elif t["ratio_review_min"] <= r <= t["ratio_review_max"]:
                nivo = max(nivo, _REVIEW)
            else:
                nivo = _REJECT

    return _NAZIVI[nivo]
