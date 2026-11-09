import zipfile
from epub.ocisti import ocisti_epub


def _mk(p, html):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("a.html", html)


def test_blockquote_goli_tekst_u_p_br_dijeli(tmp_path):
    p = tmp_path / "t.epub"
    _mk(p, '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
           '<body><blockquote>Prvi <em>redak</em><br/>Drugi redak<p>blok</p></blockquote></body></html>')
    ocisti_epub(p)
    t = zipfile.ZipFile(p).read("a.html").decode()
    assert "<blockquote><p>Prvi <em>redak</em></p><p>Drugi redak</p><p>blok</p></blockquote>" in t
    assert ocisti_epub(p)["datoteka"] == 0
