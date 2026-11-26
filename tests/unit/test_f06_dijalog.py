import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core import tipografija as T
from processing.workers import _normalizuj_dijalog_pipeline as N
from processing.workers import _ocisti_html_atribute as O


def _n(h):
    return N(h)[0]


def test_navodnici_usred_recenice_ostaju_citati():
    assert _n('<p>Gledao sam "Titanic" jučer.</p>') == "<p>Gledao sam „Titanic” jučer.</p>"
    assert _n('<p>Rekao je "Vuk" i otišao.</p>') == "<p>Rekao je „Vuk” i otišao.</p>"
    assert _n('<p>On reče: "Idem" i ode.</p>') == "<p>On reče: „Idem” i ode.</p>"


def test_replika_zadrzava_crticu():
    assert _n('<p>"Hej!"</p>') == "<p>— Hej!</p>"
    r = _n('<p>"Dobro," rekao je. "Idemo."</p>')
    assert r.startswith("<p>— Dobro") and "— Idemo." in r and '"' not in r


def test_ascii_replika_s_govornikom_ne_gubi_crticu():
    r = T.normaliziraj('<p>"Hej," reče. "Što je?"</p>')
    assert r.startswith("<p>— Hej,") and "Što je?" in r


def test_telefon_i_datum_ostaju_crtica():
    assert T.normaliziraj("<p>Zovi 555-1234 ili 12-5-2020.</p>") == "<p>Zovi 555-1234 ili 12-5-2020.</p>"


def test_rasponi_godina_i_stranica_en_crtica():
    assert T.normaliziraj("<p>Godine 1990-1995, str. 10-20.</p>") == "<p>Godine 1990–1995, str. 10–20.</p>"


def test_znak_za_inc_se_ne_brise():
    assert '5"' in _n('<p>Visok je 5" a širok 3".</p>')
    assert '3"' in _n('<p>Visok je 5" a širok 3".</p>')


def test_idempotentno():
    for h in ['<p>Gledao sam "Titanic".</p>', '<p>"Hej," reče. "Što je?"</p>', "<p>Godine 1990-1995.</p>"]:
        r = _n(h)
        assert _n(r) == r


def test_atributi_apostrof_i_tipografski_navodnici():
    assert O('<a title="it\'s" href=„x">t</a>') == '<a title="it\'s" href="x">t</a>'
    assert O("<p class=„booklyfi-dijalog\">x</p>") == '<p class="booklyfi-dijalog">x</p>'
