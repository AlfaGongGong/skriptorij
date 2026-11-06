# -*- coding: utf-8 -*-
from bs4 import BeautifulSoup

from epub.styler import (
    _navodnik_nakon_replike,
    _poredaj_po_id,
    _popravi_fragment_pocetka,
    _ukloni_dup_id,
)


def _soup(h):
    return BeautifulSoup(h, "html.parser")


def _t(s):
    return [p.get_text() for p in s.find_all("p")]


def test_dup_id_brise_drugi_primjerak():
    s = _soup('<p id="ji6135">— Vrati vijeće unutra. Imamo posla.</p>'
              '<p id="ji6135">„Vrati vijeće unutra. Imamo posla.”</p>')
    _ukloni_dup_id(s)
    assert _t(s) == ["— Vrati vijeće unutra. Imamo posla."]


def test_dup_id_razlicit_sadrzaj_ostaje():
    s = _soup('<p id="ji1">Kratko.</p>'
              '<p id="ji1">Potpuno drugaciji i znatno duzi tekst koji nema veze s prvim odlomkom.</p>')
    _ukloni_dup_id(s)
    assert len(_t(s)) == 2


def test_poredak_vraca_fragment():
    s = _soup('<p id="ji6128">A.</p><p id="ji6132">D.</p><p id="ji6135">E.</p>'
              '<p id="ji6129">B.</p><p id="ji6130">C.</p>')
    _poredaj_po_id(s)
    assert [p.get("id") for p in s.find_all("p")] == [
        "ji6128", "ji6129", "ji6130", "ji6132", "ji6135"]


def test_poredak_uredan_ostaje():
    s = _soup('<p id="ji1">A.</p><p id="ji2">B.</p><p id="ji4">C.</p>')
    assert _poredaj_po_id(s) == 0


def test_navodnik_nakon_replike():
    s = _soup('<p id="ji5080">„Prokleto <em>besmisleno</em>”, prozbori Leo. '
              '„Eto ti ga na”, promrmlja, moraš sam sebi biti heroj.” Otišao je.</p>')
    _navodnik_nakon_replike(s)
    assert "promrmlja, „moraš sam sebi biti heroj.”" in s.get_text()


def test_navodnik_balansiran_ostaje():
    h = '<p id="ji1">„Da”, reče on, a ona ode.</p>'
    s = _soup(h)
    assert _navodnik_nakon_replike(s) == 0


def test_frag_preko_sekcija_dodaje_prethodnom():
    s = _soup('<section><p id="ji3217">Leo je držao svoje govore.</p></section>'
              '<section><p id="ji3218">vojsci Anglanda. „Dok sam ja.”</p></section>')
    _popravi_fragment_pocetka(s)
    assert _t(s) == ["Leo je držao svoje govore vojsci Anglanda.", "„Dok sam ja.”"]


def test_frag_preko_sekcija_brise_ponovljen_rep():
    s = _soup('<section><p id="ji3441">Strese se od boli u laktu.</p></section>'
              '<section><p id="ji3442">u laktu. „Jedva se sjećam.”</p></section>')
    _popravi_fragment_pocetka(s)
    assert _t(s)[1] == "„Jedva se sjećam.”"


def test_frag_spaja_iza_trotocke_u_otvorenom_navodu():
    s = _soup('<p id="ji1">„Jedva se sjećam… ako je bilo dobrih razloga…</p>'
              '<p id="ji2">izgorjeli su poput magle.” Nije spomenuo.</p>')
    _popravi_fragment_pocetka(s)
    assert _t(s) == ["„Jedva se sjećam… ako je bilo dobrih razloga… izgorjeli su poput magle.”",
                     "Nije spomenuo."]
