from bs4 import BeautifulSoup

from epub.styler import _dodaj_dropcap, _naslov_lose


def test_title_tag_s_podnaslovom_je_naslov_knjige():
    assert _naslov_lose("King of Thorns: Book Two of the Broken Empire", "King of Thorns")


def test_pravi_naslovi_prolaze():
    assert not _naslov_lose("Wedding day", "King of Thorns")
    assert not _naslov_lose("Dan vjenčanja", "King of Thorns")
    assert not _naslov_lose("King's Road", "King of Thorns")


def test_kratki_prvi_odlomak_s_navodnikom_blokira_dropcap():
    dug = "Ako je ikada postojao čovjek koji stvari naziva pravim imenom, bio je to nadglednik Hobbs."
    s = BeautifulSoup("<html><body><h1>N</h1><p>„Lopatu?”, upita Hobbs.</p><p>" + dug + "</p></body></html>", "html.parser")
    assert _dodaj_dropcap(s) is False
    assert "booklyfi-dropcap" not in str(s)
    assert "booklyfi-prvi" in (s.find("p").get("class") or [])
