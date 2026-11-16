"""R5: intro, revizija, modali i toast: ugovor id-eva, kontrast, neblokirajuci fontovi."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REV = (ROOT / "templates/revizija.html").read_text("utf-8")
REVCSS = (ROOT / "static/css/revizija.css").read_text("utf-8")
DES = (ROOT / "static/css/design.css").read_text("utf-8")
INTRO = (ROOT / "templates/intro.html").read_text("utf-8")
INTROCSS = (ROOT / "static/css/intro.css").read_text("utf-8")
IDX = (ROOT / "templates/index.html").read_text("utf-8")


def _lum(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _cr(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _var(blok, ime):
    return re.search(r"--%s:\s*(#[0-9a-fA-F]{6})" % ime, blok).group(1)


def test_revizija_koristi_vanjski_css_bez_inline_style_bloka():
    assert "<style>" not in REV
    assert '/static/css/revizija.css' in REV


def test_revizija_idevi_iz_js_postoje_u_html():
    js_ids = set(re.findall(r'el\("([^"]+)"\)', REV))
    html_ids = set(re.findall(r'\bid="([^"]+)"', REV))
    assert js_ids <= html_ids, js_ids - html_ids


def test_revizija_poruka_je_live_region():
    assert re.search(r'id="poruka"[^>]*aria-live="polite"', REV) or re.search(r'aria-live="polite"[^>]*id="poruka"', REV)


def test_revizija_kontrast_gumba_svijetla_i_tamna():
    svijetla = REVCSS.split("@media (prefers-color-scheme: dark)")[0]
    tamna = REVCSS.split("@media (prefers-color-scheme: dark)")[1]
    for blok in (svijetla, tamna):
        for ime in ("ok", "danger", "neutral", "info"):
            assert _cr(_var(blok, ime), "#ffffff") >= 4.5, ime
    assert _cr(_var(svijetla, "muted"), _var(svijetla, "bg")) >= 4.5
    assert _cr(_var(tamna, "muted"), _var(tamna, "bg")) >= 4.5
    assert _cr(_var(svijetla, "tx"), _var(svijetla, "bg")) >= 7
    assert _cr(_var(tamna, "tx"), _var(tamna, "bg")) >= 7


def test_revizija_mete_dodira():
    assert "min-height: 52px" in REVCSS and ":focus-visible" in REVCSS and "prefers-reduced-motion" in REVCSS


def test_design_r5_modal_i_toast():
    assert "R5: modali i obavijesti" in DES
    assert DES.count("R5: modali i obavijesti") == 1
    assert "#toast-container" in DES and "var(--nav-h" in DES.split("R5: modali i obavijesti")[1]


def test_modali_idevi_jedinstveni():
    ids = re.findall(r'\bid="([^"]+)"', IDX)
    for m in ("download-modal", "report-modal", "preflight-modal", "confirm-modal", "toast-container"):
        assert ids.count(m) == 1, m


def test_intro_fontovi_neblokirajuci_i_skip_meta():
    ln = [l for l in INTRO.splitlines() if "fonts.googleapis.com/css2" in l or 'rel="stylesheet"' in l and "family=" in l]
    assert 'media="print"' in INTRO and "<noscript>" in INTRO
    assert "R5: intro" in INTROCSS
