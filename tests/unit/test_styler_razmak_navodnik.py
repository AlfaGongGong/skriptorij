from bs4 import BeautifulSoup
from epub.styler import _ukloni_razmak_pred_zatvarajucim as f


def _t(html):
    sp = BeautifulSoup(html, "html.parser")
    n = f(sp)
    return n, sp.get_text()


def test_novi_red_pred_zatvarajucim():
    n, t = _t("<p>\u201eUspje\u0161no.\n\u201d</p>")
    assert n == 1 and t == "\u201eUspje\u0161no.\u201d"


def test_razmak_pred_zatvarajucim():
    n, t = _t("<p>\u201eDa. \u201d reče</p>")
    assert n == 1 and "Da.\u201d" in t


def test_crtica_ostaje():
    n, t = _t("<p>\u201eJa nisam \u2014 \u201d</p>")
    assert n == 0 and t == "\u201eJa nisam \u2014 \u201d"


def test_ispravan_tekst_netaknut():
    n, t = _t("<p>\u201eDa\u201d, reče.</p>")
    assert n == 0


def test_idempotentno():
    sp = BeautifulSoup("<p>\u201eA.\n\u201d</p>", "html.parser")
    f(sp)
    assert f(sp) == 0
