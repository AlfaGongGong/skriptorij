"""R1: design.css (tokeni i osnova): kontrast WCAG AA, redoslijed učitavanja, precache."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/design.css").read_text("utf-8")


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _blok(selektor):
    m = re.search(re.escape(selektor) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert m, selektor
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", m.group(1)))


def _provjeri(t):
    for bg in ("bg-0", "bg-1", "bg-2", "bg-3"):
        assert _cr(t["tx-1"], t[bg]) >= 7, ("tx-1", bg)
        assert _cr(t["tx-2"], t[bg]) >= 7, ("tx-2", bg)
    for bg in ("bg-0", "bg-1", "bg-2"):
        assert _cr(t["tx-3"], t[bg]) >= 4.5, ("tx-3", bg)
        assert _cr(t["accent-text"], t[bg]) >= 4.5, ("accent-text", bg)
    assert _cr("#ffffff", t["accent-1"]) >= 4.5, "bijeli tekst na accent-1"


def test_tamna_tema_kontrast():
    _provjeri(_blok(":root"))


def test_svijetla_tema_kontrast():
    t = _blok("body.light")
    _provjeri(t)


def test_tokeni_postoje():
    for n in ("--sp-1", "--sp-4", "--fs-md", "--shadow-1", "--focus-ring", "--accent-text"):
        assert n + ":" in CSS, n


def test_redoslijed_ucitavanja_i_precache():
    html = (ROOT / "templates/index.html").read_text("utf-8")
    assert html.index("/static/css/style.css") < html.index("/static/css/design.css")
    assert '"/static/css/design.css"' in (ROOT / "static/sw.js").read_text("utf-8")
