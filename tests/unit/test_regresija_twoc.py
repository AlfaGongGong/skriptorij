# -*- coding: utf-8 -*-
"""
tests/unit/test_regresija_twoc.py — P1.1 (acc-2): regresije iz TWOC bugova
koje test_regresija_p0.py / test_tipografija.py ne pokrivaju.

Pokriva:
  core/text_utils.py     _ocisti_ai_markere (skida samo AI uvod na početku)
  core/tipografija.py    idempotentnost na širem korpusu, dijalog bez ASCII "
  core/kalkovi           važi / servis / kako god / Ok / izvinjavaj (+ HTML, + tipografija)
  epub/styler.py         _dodaj_dropcap (dijalog -> crtica, kratki p, prazna mapa)
  epub/normalizer.py     _strip_legacy_dropcap_span, _strip_booklyfi_dropcap
  epub/name_replacer.py  zamjena imena preko <img> drop-capa + skrivenog <span>
"""
import pytest
from bs4 import BeautifulSoup

from core.kalkovi.dijalog import DIJALOG_KALKOVI
from core.kalkovi.engine import KalkoviEngine
from core.text_utils import _automatska_korekcija, _ocisti_ai_markere
from core.tipografija import normaliziraj, normaliziraj_soup
from epub import styler
from epub.name_replacer import _word_boundary_replace
from epub.normalizer import _strip_booklyfi_dropcap, _strip_legacy_dropcap_span


# ── _ocisti_ai_markere ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ulaz,ocekivano", [
    ("Naravno! Evo prijevoda:\n<p>Tekst</p>", "<p>Tekst</p>"),
    ("Svakako, evo rezultata: Tekst", "Tekst"),
    ("Evo rezultata:\n\nTekst", "Tekst"),
    ("Izvolite:\n<p>Tekst</p>", "<p>Tekst</p>"),
    ("Izvolite!\nTekst", "Tekst"),
    ("  Tekst  ", "Tekst"),
])
def test_ai_uvod_se_skida(ulaz, ocekivano):
    assert _ocisti_ai_markere(ulaz) == ocekivano


@pytest.mark.parametrize("tekst", [
    "Naravno da jesam.",
    "Svakako ćemo doći.",
    "Izvolite sjesti.",
    "— Naravno, evo ti ga.",
    "<p>Naravno, evo ti ga.</p>",
    "Evo ga, stigao je!",
    "Rekao je: Naravno! Evo prijevoda: x",
    "Prvi red.\nNaravno! Evo prijevoda: drugi red.",
])
def test_ai_markeri_u_dijalogu_ostaju(tekst):
    assert _ocisti_ai_markere(tekst) == tekst


def test_ai_naravno_evo_u_govoru_na_pocetku_bloka():
    tekst = "Naravno, evo ti ga."
    assert _ocisti_ai_markere(tekst) == tekst


# ── tipografija: idempotentnost na širem korpusu ────────────────────────────

KORPUS = [
    '<p>On reče: "Ne znam."</p>',
    '<p>"Idemo", reče on.</p>',
    '<p><span class="dc">N</span>ail reče: "Dođi."</p>',
    "<p>-- Idemo -- reče on...</p>",
    '<p><em>"Ne</em> znam"</p>',
    "<p>Cijena 5-10 kuna,, i to je to .</p>",
    "<p>„Ne znam.” — reče on.</p>",
    "<p>— Hej!” reče.</p>",
    '<p>"Siroče otvarač</p>',
    '<p>— "Idemo" — reče on.</p>',
    '<p>Prvi.</p><p>— "Drugi" — reče.</p><p>Treći...</p>',
    'Prvi red.\n"Drugi red."\n-- treći',
    'Samo plain: "tekst" i ... trotočje',
]


@pytest.mark.parametrize("h", KORPUS)
def test_tip_idempotentno_korpus(h):
    jednom = normaliziraj(h)
    assert normaliziraj(jednom) == jednom


@pytest.mark.parametrize("h", [k for k in KORPUS if "<" in k])
def test_tip_soup_drugi_prolaz_nula(h):
    soup = BeautifulSoup(h, "html.parser")
    normaliziraj_soup(soup)
    assert normaliziraj_soup(soup) == 0


# ── dijalog: tipografski navodnici se ne vraćaju u ASCII ────────────────────

@pytest.mark.parametrize("h", [
    "<p>— „Idemo” — reče on.</p>",
    "<p>„Idemo”, reče on.</p>",
])
def test_dijalog_tipografski_ostaje(h):
    assert normaliziraj(h) == h


def test_dijalog_ascii_u_tipografske_s_crticom():
    assert normaliziraj('<p>— "Idemo" — reče on.</p>') == "<p>— „Idemo” — reče on.</p>"


@pytest.mark.parametrize("h", [
    '<p>"Idemo", reče on.</p>',
    '<p>On reče: "Ne znam." A ona: "Znam."</p>',
    '<p>— "Idemo" — reče "on".</p>',
])
def test_dijalog_nema_ascii_navodnika_nakon_normalizacije(h):
    assert '"' not in normaliziraj(h)


# ── važi / servis / kako god / Ok / izvinjavaj ──────────────────────────────

@pytest.fixture(scope="module")
def eng():
    return KalkoviEngine(DIJALOG_KALKOVI)


KALK_NEDIRANO = [
    "Važi.",
    "— Važi, dogovoreno.",
    "Vidjeli smo servise.",
    "Pričali su o servisima.",
    "Kako god ti drago.",
    "Ok, stiglo je.",
    "Izvinjavaj se koliko hoćeš.",
    "<p>— Važi, servis posuđa je skup.</p>",
]


@pytest.mark.parametrize("tekst", KALK_NEDIRANO)
def test_kalkovi_varijante_ne_diraju_tekst(eng, tekst):
    out, _ = eng.primijeni(tekst)
    assert out == tekst


@pytest.mark.parametrize("tekst", [
    "<p>— Važi, servis posuđa je skup.</p>",
    "<p>— Naravno, važi. Servis je zatvoren.</p>",
])
def test_kalkovi_pa_tipografija_ne_mijenja_tekst(eng, tekst):
    out, _ = eng.primijeni(tekst)
    assert normaliziraj(out) == tekst


# ── drop-cap ────────────────────────────────────────────────────────────────

DUGO = "Calder je dugo sjedio kraj prozora i gledao kako kiša pada na prazan trg."
DIJALOG_P = "— Idemo odmah, reče on i krenu prema vratima da ne gubi više ni trenutka."
HTML_DC = "<html><body><h1>Prvo poglavlje</h1>{}</body></html>"


def _soup(tijelo):
    return BeautifulSoup(HTML_DC.format(tijelo), "html.parser")


@pytest.fixture
def dc(monkeypatch):
    monkeypatch.setattr(styler, "DROPCAP_MAP", {"C": "C.png"})
    monkeypatch.setattr(styler, "_png_b64", lambda fname: "QUJD")


def test_dropcap_obican_paragraf(dc):
    soup = _soup(f"<p>{DUGO}</p>")
    assert styler._dodaj_dropcap(soup) is True
    p = soup.find("p")
    assert "booklyfi-prvi" in p["class"]
    assert len(p.find_all("img", class_="booklyfi-dropcap")) == 1
    assert p.contents[0].name == "img"
    assert p.get_text() == DUGO


def test_dropcap_dijalog_daje_crticu_a_ne_sliku(dc):
    soup = _soup(f"<p>{DIJALOG_P}</p>")
    assert styler._dodaj_dropcap(soup) is True
    p = soup.find("p")
    assert p.find("span", class_="booklyfi-crtica") is not None
    assert p.find("img", class_="booklyfi-dropcap") is None
    assert "booklyfi-prvi" in p["class"]


def test_dropcap_preskace_kratki_paragraf(dc):
    soup = _soup(f"<p>Kratko.</p><p>{DUGO}</p>")
    assert styler._dodaj_dropcap(soup) is True
    p1, p2 = soup.find_all("p")
    assert p1.get("class") is None
    assert "booklyfi-prvi" in p2["class"]


def test_dropcap_bez_slike_za_slovo_ne_mijenja_html(monkeypatch):
    monkeypatch.setattr(styler, "DROPCAP_MAP", {})
    soup = _soup(f"<p>{DUGO}</p>")
    prije = str(soup)
    assert styler._dodaj_dropcap(soup) is False
    assert str(soup) == prije


def test_strip_legacy_dropcap_span():
    soup = BeautifulSoup('<p><span class="dropcap">C</span>alder je došao.</p>', "html.parser")
    _strip_legacy_dropcap_span(soup)
    assert soup.find("span") is None
    assert soup.get_text() == "Calder je došao."


@pytest.mark.parametrize("h", [
    '<p><img class="booklyfi-dropcap" alt="C" src="a.png"/>alder je došao.</p>',
    '<p><span class="booklyfi-dropcap">C</span>alder je došao.</p>',
])
def test_strip_booklyfi_dropcap_vraca_slovo_i_je_idempotentan(h):
    soup = BeautifulSoup(h, "html.parser")
    _strip_booklyfi_dropcap(soup)
    assert soup.get_text() == "Calder je došao."
    jednom = str(soup)
    _strip_booklyfi_dropcap(soup)
    assert str(soup) == jednom


def test_ime_preko_img_dropcapa_i_skrivenog_spana():
    skriveni = '<span style="color:transparent;font-size:1px;line-height:0;">'
    ulaz = f'<p><img class="booklyfi-dropcap" src="a.png"/>{skriveni}K</span>lover je došao.</p>'
    ocekivano = f'<p><img class="booklyfi-dropcap" src="a.png"/>{skriveni}K</span>alder je došao.</p>'
    assert _word_boundary_replace(ulaz, "Klover", "Kalder") == ocekivano


# ── _ocisti_ai_markere: citat u tipografskim navodnicima ────────────────────

def test_ai_markeri_tipografski_navodnik_ostaje():
    tekst = "„Naravno, šefe.”"
    assert _ocisti_ai_markere(tekst) == tekst


# ── _automatska_korekcija (core/text_utils.py) ──────────────────────────────

@pytest.mark.parametrize("ulaz,ocekivano", [
    ("<p>Bio sam saglasan s tim.</p>", "<p>Bio sam suglasan s tim.</p>"),
    ("<p>Tamo je bilo preduzeće.</p>", "<p>Tamo je bilo poduzeće.</p>"),
    ("<p>Ali na kraju krajeva otišao je.</p>", "<p>Ali naposljetku otišao je.</p>"),
    ("<p>Tada nije bio u mogućnosti doći.</p>", "<p>Tada nije mogao doći.</p>"),
])
def test_korekcija_srbizmi_i_fraze(ulaz, ocekivano):
    assert _automatska_korekcija(ulaz) == ocekivano


@pytest.mark.parametrize("h", [
    "",
    "<p>— Važi, servis je zatvoren.</p>",
    "<p>— Naravno, važi. Servis je zatvoren.</p>",
    '<p class="x" id="a">Tekst…</p>',
    "<p>On reče: „Ne znam.”</p>",
    "<p>Pre</p><p>duzeće</p>",
])
def test_korekcija_cist_tekst_ostaje(h):
    assert _automatska_korekcija(h) == h


def test_korekcija_tagovi_i_atributi_netaknuti():
    ulaz = '<p class="saglasan" id="preduzeće">Bio sam saglasan.</p>'
    ocekivano = '<p class="saglasan" id="preduzeće">Bio sam suglasan.</p>'
    assert _automatska_korekcija(ulaz) == ocekivano


def test_korekcija_inline_tag_ostaje():
    ulaz = "<p>Bio je <em>saglasan</em> s tim.</p>"
    assert _automatska_korekcija(ulaz) == "<p>Bio je <em>suglasan</em> s tim.</p>"


@pytest.mark.parametrize("h", [
    "<p>Bio sam saglasan s tim.</p>",
    "<p>Ali na kraju krajeva otišao je.</p>",
    "<p>Tamo je bilo preduzeće.</p>",
])
def test_korekcija_idempotentna(h):
    jednom = _automatska_korekcija(h)
    assert _automatska_korekcija(jednom) == jednom


@pytest.mark.parametrize("ulaz", [
    "<p>Saglasan sam.</p>",
    "<p>Preduzeće je zatvoreno.</p>",
    "<p>Morao je da ide kući.</p>",
    "<p>Na kraju krajeva, otišao je.</p>",
])
def test_korekcija_cuva_veliko_pocetno_slovo(ulaz):
    out = _automatska_korekcija(ulaz)
    assert BeautifulSoup(out, "html.parser").get_text()[0].isupper()


def test_korekcija_znao_je_da_ne_spaja_rijeci():
    out = _automatska_korekcija("<p>Tada znao je da vidi sve.</p>")
    assert "jevidi" not in out


def test_korekcija_ne_dira_html_komentar():
    ulaz = "<p>Tekst.</p><!-- saglasan -->"
    assert _automatska_korekcija(ulaz) == ulaz
