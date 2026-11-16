"""R2a: pogledi i donja navigacija: ugovor HTML/CSS/JS (id-evi i data-tab ostaju)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "templates/index.html").read_text("utf-8")
CSS = (ROOT / "static/css/design.css").read_text("utf-8")
SW = (ROOT / "static/sw.js").read_text("utf-8")
VJS = ROOT / "static/js/ui/views.js"

GRUPA = {"tab-quality": "kvaliteta", "tab-epub": "knjiga", "tab-review": "knjiga", "tab-history": "knjiga",
         "panel-stil": "alati", "panel-tts-filter": "alati", "tab-expert": "alati", "tab-monitor": "alati"}


def _tab_gumbi():
    return re.findall(r'<button class="tab-btn[^"]*"[^>]*data-tab="([^"]+)"[^>]*data-group="([^"]+)"', HTML)


def test_svih_8_tabova_ima_grupu():
    nadjeno = dict(_tab_gumbi())
    assert nadjeno == GRUPA


def test_svaki_tab_ima_panel():
    ids = set(re.findall(r'\bid="([^"]+)"', HTML))
    for t in GRUPA:
        assert t in ids, t


def test_donja_navigacija_4_pogleda():
    nav = re.search(r'<nav id="bottom-nav".*?</nav>', HTML, re.S)
    assert nav
    assert re.findall(r'data-view="([^"]+)"', nav.group(0)) == ["rad", "kvaliteta", "knjiga", "alati"]


def test_views_js_ukljucen_i_precache():
    assert "/static/js/ui/views.js" in HTML
    assert '"/static/js/ui/views.js"' in SW
    assert "booklyfi-cache-v9" in SW
    assert VJS.exists()


def test_css_pravila_pogleda():
    assert 'body[data-view="rad"] .card-tabs' in CSS
    assert "#setup-panel" in CSS and "#dashboard-panel" in CSS
    assert "--nav-h" in CSS


def test_ciljevi_dodira_vece_od_44px():
    m = re.search(r"--nav-h:\s*(\d+)px", CSS)
    assert m and int(m.group(1)) >= 44


@pytest.mark.skipif(shutil.which("node") is None, reason="node nije instaliran")
def test_views_js_sintaksa():
    r = subprocess.run(["node", "--check", str(VJS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
