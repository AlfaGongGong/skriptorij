from bs4 import BeautifulSoup

from epub.styler import _stil_ocisti_p


def _s(html):
    return BeautifulSoup(html, "html.parser")


def _ps(soup):
    return [p.get_text() for p in soup.find_all("p")]


def test_spaja_presjecen_pasus():
    s = _s("<div><p>Zakleo se da će se kloniti, ali problem je bio u tome što se</p>\n<p>nevolja nije htjela kloniti njega.</p></div>")
    assert _stil_ocisti_p(s) == (1, 0)
    assert _ps(s) == ["Zakleo se da će se kloniti, ali problem je bio u tome što se nevolja nije htjela kloniti njega."]


def test_ne_spaja_kad_prethodni_zavrsava_interpunkcijom():
    s = _s("<div><p>Prvi je gotov.</p><p>drugi pocinje malim.</p></div>")
    assert _stil_ocisti_p(s) == (0, 0)
    assert len(_ps(s)) == 2


def test_ne_spaja_kad_sljedeci_pocinje_velikim():
    s = _s("<div><p>Prvi bez kraja</p><p>Drugi pocinje velikim.</p></div>")
    assert _stil_ocisti_p(s) == (0, 0)


def test_lanac_od_tri():
    s = _s("<div><p>a b c</p><p>d e f</p><p>g h i.</p></div>")
    assert _stil_ocisti_p(s) == (2, 0)
    assert _ps(s) == ["a b c d e f g h i."]


def test_crtica_na_kraju_bez_razmaka():
    s = _s("<div><p>sester-</p><p>fajcanje po strani.</p></div>")
    _stil_ocisti_p(s)
    assert _ps(s) == ["sester-fajcanje po strani."]


def test_cuva_em_unutar_spojenog():
    s = _s("<div><p>Rekao je <em>jasno</em> da se</p><p>vraca kuci.</p></div>")
    _stil_ocisti_p(s)
    assert s.find("em") is not None
    assert _ps(s) == ["Rekao je jasno da se vraca kuci."]


DUGI = " ".join("rijec%d" % i for i in range(25)) + "."


def test_brise_blizak_duplikat():
    s = _s("<div><p>%s</p><p>Jedan kratak.</p><p>Dva kratak.</p><p>%s</p></div>" % (DUGI, DUGI))
    assert _stil_ocisti_p(s) == (0, 1)
    assert len(_ps(s)) == 3


def test_kratki_duplikat_ostaje():
    s = _s("<div><p>Da.</p><p>Ne.</p><p>Da.</p></div>")
    assert _stil_ocisti_p(s) == (0, 0)
    assert len(_ps(s)) == 3


def test_daleki_duplikat_ostaje():
    mid = "".join("<p>Razlicit odlomak broj %d.</p>" % i for i in range(14))
    s = _s("<div><p>%s</p>%s<p>%s</p></div>" % (DUGI, mid, DUGI))
    assert _stil_ocisti_p(s) == (0, 0)


def test_idempotentno():
    s = _s("<div><p>a b c</p><p>d e f.</p></div>")
    _stil_ocisti_p(s)
    assert _stil_ocisti_p(s) == (0, 0)
