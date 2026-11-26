# -*- coding: utf-8 -*-
"""
tests/unit/test_regresija_p0.py — P1.1 regresioni testovi za ispravke 2026-11-04.

Pokriva:
  P0.2  core/tipografija.py          (navodnici, crtice, trotočje, idempotentnost)
  P0.3  epub/name_replacer.py        (tag-aware zamjena imena, čuvanje casinga)
  P0.6  core/text_utils.py           (_strip_out_tag / _smart_extract)
  ENG   core/kalkovi/engine.py       (_repl čuva malo početno slovo)
  P1.4  core/kalkovi/dijalog.py      (zamrznuta pravila: važi, servis, kako god, OK, izvini)
"""
import pytest

from core import tipografija as tip
from core.kalkovi.engine import KalkoviEngine
from core.kalkovi.dijalog import DIJALOG_KALKOVI
from core.text_utils import _smart_extract, _strip_out_tag
from epub.name_replacer import _apply_replacements_to_html, _word_boundary_replace

OTV, ZAT = "„", "”"


# ── ENGINE: case-preserve ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
def eng():
    return KalkoviEngine(DIJALOG_KALKOVI)


@pytest.mark.parametrize("ulaz,ocekivano", [
    ("A šta ti je?", "A što ti je?"),
    ("Šta ti je?", "Što ti je?"),
    ("Znaš šta to znači.", "Znaš što to znači."),
])
def test_engine_case(eng, ulaz, ocekivano):
    out, _ = eng.primijeni(ulaz)
    assert out == ocekivano


def test_engine_nema_velikog_slova_usred_recenice(eng):
    out, _ = eng.primijeni("Reci mi šta hoćeš.")
    assert "Što" not in out and "što" in out


def test_engine_html_tag_ostaje(eng):
    out, _ = eng.primijeni('<p class="šta">šta je</p>')
    assert 'class="šta"' in out and "što je" in out


# ── P1.4: zamrznuti kalkovi ─────────────────────────────────────────────────

@pytest.mark.parametrize("tekst", [
    "Pravilo važi za sve.",
    "Važi, dogovoreno je.",
    "Odnijeli smo auto na servis.",
    "Servis posuđa je skup.",
    "Kako god hoćeš.",
    "OK, idemo.",
    "Izvini, nisam htio.",
    "Izvinite na smetnji.",
])
def test_zamrznuti_kalkovi_ne_diraju_tekst(eng, tekst):
    out, _ = eng.primijeni(tekst)
    assert out == tekst


def test_dijalog_nema_aktivnih_zamrznutih_pravila():
    aktivni = " ".join(p for p, _ in (e[:2] for e in DIJALOG_KALKOVI))
    for rijec in ("važi", "servis", "kako", "OK", "izvin"):
        assert rijec not in aktivni, f"pravilo za '{rijec}' opet aktivno"


# ── P0.6: <out> omotač ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ulaz,ocekivano", [
    ("<out>Tekst</out>", "Tekst"),
    ("<OUT>Tekst</OUT>", "Tekst"),
    ("<out>Tekst<\\/out>", "Tekst"),
    ("<out >Tekst</ out>", "Tekst"),
    ("Bez omotača", "Bez omotača"),
    ("", ""),
])
def test_strip_out_tag(ulaz, ocekivano):
    assert _strip_out_tag(ulaz) == ocekivano


def test_smart_extract_out_prije_jsona():
    raw = '<out>{"finalno_polirano": "Dobar dan."}</out>'
    assert _smart_extract(raw) == "Dobar dan."


def test_smart_extract_out_oko_plain_teksta():
    assert "<out>" not in _smart_extract("<out>Običan tekst.</out>")


# ── P0.2: tipografija ───────────────────────────────────────────────────────

def test_tip_ascii_navodnici_u_tipografske():
    out = tip.normaliziraj('<p>Rekao je "dobar dan" svima.</p>')
    assert f"{OTV}dobar dan{ZAT}" in out and '"dobar' not in out


def test_tip_replika_postaje_crtica():
    out = tip.normaliziraj('<p>"Idemo odavde."</p>')
    assert out == "<p>— Idemo odavde.</p>"


def test_tip_trotocje():
    assert tip.normaliziraj("<p>Pa...</p>") == "<p>Pa…</p>"


def test_tip_navodnik_preko_inline_taga():
    out = tip.normaliziraj('<p>Rekao je "to je <em>vrlo</em> važno" i otišao.</p>')
    assert out.count(OTV) == 1 and out.count(ZAT) == 1 and "<em>vrlo</em>" in out


def test_tip_atributi_netaknuti():
    ulaz = '<p class="a" title="x...y">Tekst</p>'
    assert 'title="x...y"' in tip.normaliziraj(ulaz)


@pytest.mark.parametrize("ulaz", [
    '<p>Rekao je "dobar dan" svima.</p>',
    '<p>"Idemo." rekao je.</p>',
    "<p>Pa... ne znam -- možda.</p>",
    f"<p>{OTV}Već gotovo{ZAT}</p>",
])
def test_tip_idempotentno(ulaz):
    jednom = tip.normaliziraj(ulaz)
    assert tip.normaliziraj(jednom) == jednom


def test_tip_provjeri_cisto_nakon_normalizacije():
    out = tip.normaliziraj('<p>Rekao je "dobar dan"... i otišao.</p>')
    assert tip.provjeri(out) == []


def test_tip_provjeri_hvata_ascii():
    assert tip.provjeri('<p>Rekao je "x"</p>')
    with pytest.raises(AssertionError):
        tip.provjeri('<p>Rekao je "x"</p>', strogo=True)


# ── P0.3: tag-aware imena ───────────────────────────────────────────────────

def test_ime_obicna_zamjena():
    assert _word_boundary_replace("<p>Nail je došao.</p>", "Nail", "Nejl") == "<p>Nejl je došao.</p>"


def test_ime_dropcap_span():
    out = _word_boundary_replace('<p><span class="dc">N</span>ail je došao.</p>', "Nail", "Nejl")
    assert out == '<p><span class="dc">N</span>ejl je došao.</p>'


def test_ime_em_podijeljeno():
    out = _word_boundary_replace("<p><em>Nai</em>l je došao.</p>", "Nail", "Nejl")
    assert "<em>" in out and "</em>" in out
    assert out.replace("<em>", "").replace("</em>", "") == "<p>Nejl je došao.</p>"


def test_ime_ne_spaja_preko_blok_tagova():
    ulaz = "<p>Na</p><p>il</p>"
    assert _word_boundary_replace(ulaz, "Nail", "Nejl") == ulaz


def test_ime_ne_kvari_podrijeci():
    ulaz = "<p>Nailon je tkanina.</p>"
    assert _word_boundary_replace(ulaz, "Nail", "Nejl") == ulaz


def test_ime_atribut_netaknut():
    ulaz = '<p title="Nail">Nail</p>'
    out = _word_boundary_replace(ulaz, "Nail", "Nejl")
    assert 'title="Nail"' in out and ">Nejl<" in out


def test_ime_cuva_casing():
    assert _word_boundary_replace("<p>NAIL viče.</p>", "Nail", "Nejl") == "<p>NEJL viče.</p>"


def test_ime_apply_lista():
    html, primijenjeno = _apply_replacements_to_html(
        "<p>Nail i Nail.</p>", [("Nail", "Nejl"), ("X", "X")]
    )
    assert html == "<p>Nejl i Nejl.</p>" and primijenjeno == [("Nail", "Nejl")]
