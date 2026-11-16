"""L52: tabovi: bez preklapanja polla, crtanje audita samo kad je vidljivo, Pregled ograniceno, fontovi neblokirajuci."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/main.js").read_text("utf-8")
HTML = (ROOT / "templates/index.html").read_text("utf-8")


def test_poll_status_bez_preklapanja():
    assert "_pollStatusBusy" in JS and "finally" in JS.split("async function pollStatus", 1)[1][:600]


def test_audit_crta_se_samo_kad_vidljivo():
    blok = JS.split("_key52", 1)[1][:900]
    assert 'data-view' in blok and "tab-expert" in blok and "_liveAuditKey52" in blok


def test_pregled_ogranicen():
    assert "_MAX52 = 150" in JS and "btn-epub-show-all" in JS


def test_id_show_all_jedinstven_u_html():
    assert HTML.count('id="btn-epub-show-all"') == 0


def test_fontovi_neblokirajuci():
    ln = [l for l in HTML.splitlines() if "fonts.googleapis.com/css2" in l and "<link" in l]
    assert ln and all('media="print"' in l or "<noscript>" in l for l in ln)
