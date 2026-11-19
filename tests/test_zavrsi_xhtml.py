from core import zavrsi

def test_blok_html_i_xhtml():
    for s in ["part0013.xhtml_blok_2", "part0013.xhtml_blok_2.chk",
              "part0004.html_blok_0", "CR!AB_split_011.html_blok_10.chk"]:
        assert zavrsi._BLOK.match(s), s
    m = zavrsi._BLOK.match("part0013.xhtml_blok_2")
    assert m.group(1) == "part0013.xhtml" and m.group(2) == "2"
    assert not zavrsi._BLOK.match("part0013.txt_blok_2")
