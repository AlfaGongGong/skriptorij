# -*- coding: utf-8 -*-
import pytest

from core.tipografija import normaliziraj, normaliziraj_soup, provjeri
from bs4 import BeautifulSoup

NE_MIJENJA = [
    "<p>— Idemo — reče on.</p>",
    "<p>Došli su u pet sati i sjeli.</p>",
    "<p>On reče: „Ne znam.”</p>",
    '<p class="x" id="a">Tekst…</p>',
    "<p>— Šta ti je? — upita.</p>",
    "<p>— Naravno, važi. Servis je zatvoren.</p>",
]


@pytest.mark.parametrize("h", NE_MIJENJA)
def test_ne_mijenja_ispravno(h):
    assert normaliziraj(h) == h


def test_ascii_u_tipografske():
    assert normaliziraj('<p>On reče: "Ne znam."</p>') == "<p>On reče: „Ne znam.”</p>"


def test_preko_em_taga():
    r = normaliziraj('<p>Reče <em>"Idemo</em> sad".</p>')
    assert r == "<p>Reče <em>„Idemo</em> sad”.</p>"


def test_dropcap_i_atributi():
    h = '<p class="dc"><span class="cap">C</span>lover reče "da".</p>'
    r = normaliziraj(h)
    assert 'class="dc"' in r and 'class="cap"' in r
    assert "„da”" in r and "<span class=\"cap\">C</span>lover" in r


def test_vodeci_par_u_crticu():
    assert normaliziraj('<p>"Idemo kući," reče.</p>') == "<p>— Idemo kući, reče.</p>"


def test_sirote_u_dash_odlomku():
    assert normaliziraj("<p>— Idemo kući.”</p>") == "<p>— Idemo kući.</p>"
    assert normaliziraj('<p>— Idemo kući." Reče.</p>') == "<p>— Idemo kući. Reče.</p>"


def test_vodeci_siroce_otvarac():
    assert normaliziraj('<p>"Idemo kući.</p>') == "<p>— Idemo kući.</p>"


def test_crtice_i_trotocje():
    assert normaliziraj("<p>- Ne... ne znam.</p>") == "<p>— Ne… ne znam.</p>"
    assert normaliziraj("<p>-- Ne.</p>") == "<p>— Ne.</p>"


def test_vise_odlomaka_govor_u_crticama():
    # L50 (odluka 17.11.): replika u navodnicima na početku odlomka postaje crtica
    h = "<p>„Dug govor koji se nastavlja</p><p>„i dalje traje.”</p>"
    assert normaliziraj(h) == "<p>— Dug govor koji se nastavlja</p><p>— i dalje traje.</p>"


def test_plain_tekst():
    assert normaliziraj('Reče "da".\n- Ne.') == "Reče „da”.\n— Ne."


def test_idempotentno():
    korpus = [
        '<p>Reče <em>"Idemo</em> sad". A... on?</p>',
        '<p>"Idemo kući," reče.</p>', "<p>— Idemo kući.”</p>",
        '<p>"Idemo kući.</p>', '<p><span>C</span>lover reče "da".</p>',
        "<p>-- Da -- ne.</p>", '<p>Reče "a" i "b".</p>',
    ]
    for h in korpus:
        a = normaliziraj(h)
        assert normaliziraj(a) == a


def test_provjeri():
    assert provjeri("<p>— Idemo — reče.</p>") == []
    assert provjeri('<p>Reče "da".</p>')
    assert provjeri("<p>— Idemo.”</p>")
    with pytest.raises(AssertionError):
        provjeri('<p>Reče "da".</p>', strogo=True)


def test_soup_inplace():
    s = BeautifulSoup('<p>Reče "da".</p>', "html.parser")
    assert normaliziraj_soup(s) == 1
    assert str(s) == "<p>Reče „da”.</p>"
