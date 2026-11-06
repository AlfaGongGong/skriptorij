from bs4 import BeautifulSoup

from epub.styler import _navodnici_popravi


def _t(html):
    s = BeautifulSoup(html, "html.parser")
    n = _navodnici_popravi(s)
    return n, s.get_text()


def test_a_izgubljen_zatvarajuci_prije_glagola():
    n, t = _t("<p>\u201eOv\u010detina, izustila je hvatajući zrak.</p>")
    assert n == 1
    assert t == "\u201eOv\u010detina\u201d, izustila je hvatajući zrak."


def test_a_drugi_navod_ostaje():
    n, t = _t("<p>\u201eDa, uzdahnuo je Klover, \u201ea pobjednik dobiva nagradu. Rani grob.\u201d</p>")
    assert n == 1
    assert t.startswith("\u201eDa\u201d, uzdahnuo je Klover, \u201ea pobjednik")


def test_a_cuva_em():
    s = BeautifulSoup("<p>\u201eProkleto <em>besmisleno</em>, prozbori Leo kroz zube.</p>", "html.parser")
    assert _navodnici_popravi(s) == 1
    assert s.find("em") is not None
    assert s.get_text() == "\u201eProkleto besmisleno\u201d, prozbori Leo kroz zube."


def test_b_crtica_umjesto_otvarajuceg():
    n, t = _t("<p>\u201eSamo radiš! Ali svejedno.\u201d Stand se nasmijao smijehom. \u2014 Više ovčetine za mene!\u201d Zatim je ošinuo uzde.</p>")
    assert n == 1
    assert "smijehom. \u201eVi\u0161e ov\u010detine za mene!\u201d Zatim" in t.replace("Više", "Vi\u0161e").replace("ovčetine", "ov\u010detine")


def test_b_ne_dira_pasus_koji_pocinje_crticom():
    n, t = _t("<p>\u2014 \u010cujem vas.\u201d</p>")
    assert n == 0
    assert t == "\u2014 \u010cujem vas.\u201d"


def test_c_razmak_crtica_navodnik():
    n, t = _t("<p>\u201eStao sam na stranu pobjednika \u2014 \u201d</p>")
    assert n == 1
    assert t.endswith("pobjednika \u2014\u201d")


def test_uravnotezen_ostaje():
    n, t = _t("<p>\u201eDobro\u201d, reče on.</p>")
    assert n == 0
    assert t == "\u201eDobro\u201d, reče on."


def test_idempotentno():
    s = BeautifulSoup("<p>\u201eOv\u010detina, izustila je.</p>", "html.parser")
    _navodnici_popravi(s)
    assert _navodnici_popravi(s) == 0


def test_c_balansirani_pasus_razmak_crtica_navodnik():
    n, t = _t("<p>\u201eReci mi\u201d, rekla je. \u201eNe mogu otići bez nje, ja \u2014 \u201d</p>")
    assert n >= 1
    assert "\u2014 \u201d" not in t
    assert t.endswith("ja \u2014\u201d")
