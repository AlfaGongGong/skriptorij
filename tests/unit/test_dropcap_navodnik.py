from bs4 import BeautifulSoup

from epub.styler import _dodaj_dropcap

TEKST = "Podijeljena bol, moj brate, nije udvostručena nego prepolovljena. Što su meni godine? Poput boli."


def test_navodnik_bez_crtice():
    s = BeautifulSoup(f"<body><h1>X</h1><p>„{TEKST}”</p></body>", "html.parser")
    _dodaj_dropcap(s)
    assert s.find("span", class_="booklyfi-crtica") is None
    assert s.find("p").get_text().startswith("„")


def test_crtica_replike_ostaje():
    s = BeautifulSoup(f"<body><h1>X</h1><p>— {TEKST}</p></body>", "html.parser")
    assert _dodaj_dropcap(s) is True
    assert s.find("span", class_="booklyfi-crtica") is not None
