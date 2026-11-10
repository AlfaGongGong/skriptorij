import os
import re
import sys

KOR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, KOR)


def _citaj(p):
    return open(os.path.join(KOR, p), encoding="utf-8").read()


def test_nema_dupliciranih_id():
    ids = re.findall(r'\bid="([^"]+)"', _citaj("templates/index.html"))
    dup = sorted({i for i in ids if ids.count(i) > 1})
    assert not dup, dup


def test_nove_klase_postoje_u_css():
    h, c = _citaj("templates/index.html"), _citaj("static/css/style.css")
    for k in ("u-ml-auto", "u-ml-8", "u-ml-12", "u-tx3", "u-empty-icon", "u-empty-hint",
              "btn-tone-emerald", "btn-tone-accent2", "btn-tone-amber", "btn-tone-rose",
              "btn-tone-violet", "progress-track-sm", "link-revizija"):
        assert k in h, "nije u html: " + k
        assert "." + k in c, "nije u css: " + k
    assert "#p26-revizija-fab" in c


def test_js_elementi_zadrzali_inline():
    h = _citaj("templates/index.html")
    for i in ("progress-bar", "qs-print-ready-bar", "modal-pct-fill", "qs-relektura-banner", "st-result-card"):
        assert re.search(r'id="%s"[^>]*style="' % i, h), i


def test_fab_i_revizija_link():
    h = _citaj("templates/index.html")
    assert 'id="p26-revizija-fab"' in h and 'href="/revizija"' in h
