from bs4 import BeautifulSoup


def test_naslovi_iz_chk(tmp_path):
    import epub.styler as ST
    ck = tmp_path / "checkpoints"
    ck.mkdir()
    (ck / "AT5_split_011.html_blok_0.chk").write_text(
        '<!-- chunk_sha:x --> <h1 class="c"><span><em>Dan vjen\u010danja</em></span></h1><p>Tekst</p>', encoding="utf-8")
    (ck / "AT5_split_013.html_blok_0.chk").write_text(
        '<!-- chunk_sha:y --> <h1><em>Wedding day</em></h1><p>Tekst</p>', encoding="utf-8")
    (ck / "AT5_split_014.html_blok_0.chk").write_text('<p>Epigraf</p>', encoding="utf-8")
    (ck / "AT5_split_015.html_blok_0.chk").write_text('<h1>7</h1><p>x</p>', encoding="utf-8")
    r = ST._naslovi_iz_chk(tmp_path)
    assert r == {"split_011.html": "Dan vjen\u010danja", "split_013.html": "Dan vjen\u010danja"}
    assert ST._naslovi_iz_chk(None) == {}


def test_normaliziraj_naslov_dnevnika():
    import epub.styler as ST
    s = BeautifulSoup("<html><body><p>FROM DNEVNIKA KATE RINE SCORRON</p><p>Tekst</p></body></html>", "html.parser")
    assert ST._normaliziraj_naslov_dnevnika(s) is True
    assert s.find("p").get_text() == "IZ DNEVNIKA KATHERINE AP SCORRON"
    assert ST._normaliziraj_naslov_dnevnika(s) is False
    s2 = BeautifulSoup("<html><body><p>Obi\u010dan odlomak</p></body></html>", "html.parser")
    assert ST._normaliziraj_naslov_dnevnika(s2) is False
