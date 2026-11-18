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


def test_brojevi_iz_chk(tmp_path):
    import epub.styler as ST
    ck = tmp_path / "checkpoints"
    ck.mkdir()
    (ck / "AT5_split_010.html_blok_0.chk").write_text('<!-- c --> <h1><em>3</em></h1>', encoding="utf-8")
    (ck / "AT5_split_011.html_blok_0.chk").write_text('<h1>Dan vjen\u010danja</h1><p>x</p>', encoding="utf-8")
    assert ST._brojevi_iz_chk(tmp_path) == {"split_010.html": "3"}
    assert ST._naslovi_iz_chk(tmp_path) == {"split_011.html": "Dan vjen\u010danja"}


def test_nadi_skr_za_fajlove(tmp_path, monkeypatch):
    import epub.styler as ST
    monkeypatch.setattr("config.settings.CHECKPOINT_BASE_DIR", str(tmp_path))
    ck = tmp_path / "_skr_Knjiga" / "checkpoints"
    ck.mkdir(parents=True)
    for n in ("011", "013", "014"):
        (ck / ("AT5_split_%s.html_blok_0.chk" % n)).write_text("<p>x</p>", encoding="utf-8")
    drugi = tmp_path / "_skr_Druga" / "checkpoints"
    drugi.mkdir(parents=True)
    (drugi / "ZZZ_split_011.html_blok_0.chk").write_text("<p>x</p>", encoding="utf-8")
    imena = ["OEBPS/CRXXAT5_split_011.html", "OEBPS/CRXXAT5_split_013.html", "OEBPS/CRXXAT5_split_014.html"]
    assert ST._nadi_skr_za_fajlove(imena) == tmp_path / "_skr_Knjiga"
    assert ST._nadi_skr_za_fajlove(["OEBPS/a.html"]) is None
