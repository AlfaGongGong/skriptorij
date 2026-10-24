"""
tests/golden/test_metrics.py
Golden test za core/metrics.py — deterministicki brojaci (vec postoji u benchmarks/).
Ovde: brzi smoke za hash stabilnost.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_metrics_deterministic_hash():
    """Isti tekst → iste metrike (determinizam)."""
    import hashlib
    import json

    from core.metrics import compute_metrics

    text = "<p>On je rekao da će doći. Lepo vreme danas.</p>"
    m1 = compute_metrics(text)
    m2 = compute_metrics(text)

    h1 = hashlib.sha256(json.dumps(m1, sort_keys=True).encode()).hexdigest()[:16]
    h2 = hashlib.sha256(json.dumps(m2, sort_keys=True).encode()).hexdigest()[:16]
    assert h1 == h2, "metrike nisu deterministicke"

    # Kljucevi moraju biti isti
    assert set(m1.keys()) == set(m2.keys())


def test_metrics_classify_consistency():
    """classify_metrics na istim metrikama → isti rezultat."""
    from core.metrics import classify_metrics, compute_metrics

    text = "<p>Lijepo vrijeme danas.</p>"
    m = compute_metrics(text)
    c1 = classify_metrics(m)
    c2 = classify_metrics(m)
    assert c1 == c2
    assert c1 in ("OK", "REVIEW", "REJECT", "TRUNCATED")
