# -*- coding: utf-8 -*-
from bs4 import BeautifulSoup

from epub.styler import _popravi_fragment_pocetka


def _p(html):
    s = BeautifulSoup(html, "html.parser")
    _popravi_fragment_pocetka(s)
    return [p.get_text() for p in s.find_all("p")]


def test_ponovljen_rep_se_brise():
    t = _p('<p id="ji1">Strese se od boli u laktu.</p>'
           '<p id="ji2">u laktu. „Jedva se sjećam.”</p>')
    assert t[1] == "„Jedva se sjećam.”"


def test_odbaceni_rep_se_vraca_prethodnom():
    t = _p('<p id="ji3217">Leo je napuhao prsa, dok je držao svoje govore.</p>'
           '<p id="ji3218">vojsci Anglanda. „Dok sam ja na čelu.”</p>')
    assert t[0] == "Leo je napuhao prsa, dok je držao svoje govore vojsci Anglanda."
    assert t[1] == "„Dok sam ja na čelu.”"


def test_neuzastopni_id_ostaje():
    h = ('<p id="ji6135">— Vrati vijeće unutra.</p>'
         '<p id="ji6129">tebi, prije vjenčanja, da gledaš na to kao na odnos.” Dalje.</p>')
    assert _p(h) == ["— Vrati vijeće unutra.",
                     "tebi, prije vjenčanja, da gledaš na to kao na odnos.” Dalje."]


def test_obican_pasus_ostaje():
    h = '<p id="ji1">Prvi.</p><p id="ji2">Drugi pasus počinje velikim.</p>'
    assert _p(h) == ["Prvi.", "Drugi pasus počinje velikim."]
