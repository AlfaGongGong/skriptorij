from epub.styler import _zavrsava_url_ili_domenom as f


def test_url_kraj_o_autoru():
    t = ("Zivi u Bangoru, u Maineu, sa suprugom Tabithom King. UPOZNAJTE AUTORE "
         "NA SimonandSchuster.com authors.simonandschuster.com/Stephen-King")
    assert f(t)


def test_www_i_http():
    assert f("Vidi vise na www.primjer.ba/knjiga")
    assert f("Vidi https://primjer.org/a/b")


def test_domena_bez_putanje():
    assert f("Posjetite SimonandSchuster.com")


def test_obican_prekid_nije_url():
    assert not f("Rekao je da ce doci i onda se")


def test_tacka_u_sredini_nije_url():
    assert not f("a onda je rekao kraj.Sljedece")


def test_prazno():
    assert not f("")
    assert not f(None)
