from bs4 import BeautifulSoup

from epub.styler import _apostrof_fix


def _s(h):
    return BeautifulSoup(h, "html.parser")


def test_apostrof_postaje_apostrof():
    s = _s("<p>u Skarling\u201es Chairu</p>")
    assert _apostrof_fix(s) == 1
    assert s.get_text() == "u Skarling\u2019s Chairu"


def test_pravi_navodnik_ostaje():
    s = _s("<p>Rekao je: \u201eda\u201d, i otisao.</p>")
    assert _apostrof_fix(s) == 0
    assert "\u201eda\u201d" in s.get_text()


def test_idempotentno():
    s = _s("<p>Skarling\u201es</p>")
    _apostrof_fix(s)
    assert _apostrof_fix(s) == 0


def test_normaliziraj_brise_siroce_u_dijalogu():
    from core.tipografija import normaliziraj_soup
    s = _s("<p>\u2014 \u010cujem vas.\u201d</p>")
    normaliziraj_soup(s)
    assert s.get_text() == "\u2014 \u010cujem vas."
