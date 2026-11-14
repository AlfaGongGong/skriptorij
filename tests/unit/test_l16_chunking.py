from bs4 import BeautifulSoup

from core.chunking import chunk_html

W = " ".join(("r%d." % i) if i % 9 == 0 else ("r%d" % i) for i in range(3000))


def _wc(h):
    return len(BeautifulSoup(h, "html.parser").get_text().split())


def _tekst(chunks):
    return " ".join(BeautifulSoup("".join(chunks), "html.parser").get_text(" ").split())


def _provjeri(html):
    c = chunk_html(html, 500)
    assert len(c) > 1
    assert max(_wc(x) for x in c) <= 700
    assert _tekst(c) == " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())


def test_goli_tekst_u_body():
    _provjeri("<html><body>" + W + "</body></html>")


def test_goli_tekst_u_divu():
    _provjeri("<html><body><div>" + W + "</div></body></html>")


def test_p_u_spanu():
    _provjeri("<html><body><p><span>" + W + "</span></p></body></html>")


def test_p_u_emu():
    _provjeri("<html><body><p><em>" + W + "</em></p></body></html>")


def test_blockquote_goli_tekst():
    _provjeri("<html><body><blockquote>" + W + "</blockquote></body></html>")


def test_normalni_blokovi_nepromijenjeni():
    html = "<html><body>" + "".join(
        "<p>" + " ".join("kuca" for _ in range(60)) + ".</p>" for _ in range(40)
    ) + "</body></html>"
    c = chunk_html(html, 500)
    assert len(c) == 5
    assert all(x.count("<p>") == 8 for x in c)
