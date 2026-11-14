from core.glosar_ekstrakcija import autori_iz_teksta, je_pozadinski_fajl, opf_autori


def test_pozadinski_fajlovi():
    for n in ("OEBPS/title.xhtml", "copyright.xhtml", "text/aboutauthor.xhtml", "alsoby.xhtml", "cover.xhtml"):
        assert je_pozadinski_fajl(n), n
    for n in ("OEBPS/chapter001.xhtml", "part0007_split_000.html", "introduction.xhtml"):
        assert not je_pozadinski_fajl(n), n


def test_autori_iz_teksta():
    a = autori_iz_teksta("Introduction by Helen Simpson. Copyright (c) 1979 Angela Carter")
    assert {"Helen", "Simpson", "Angela", "Carter"} <= a


def test_lik_nije_autor():
    assert "Lyon" not in autori_iz_teksta("He was driven by Mr Lyon to the house. Beauty came by Lyon.")


def test_opf(tmp_path):
    import zipfile

    p = tmp_path / "k.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("content.opf", "<package><dc:creator opf:role='aut'>Carter, Angela</dc:creator></package>")
    assert opf_autori(str(p)) == {"Carter", "Angela"}
