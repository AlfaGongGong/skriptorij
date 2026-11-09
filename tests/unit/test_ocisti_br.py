import zipfile
from epub.ocisti import ocisti_epub


def _mk(p, html):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("a.html", html)


def test_br_u_body_uklonjen_a_u_p_ostaje(tmp_path):
    p = tmp_path / "t.epub"
    _mk(p, '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
           '<body><p>a<br/>b</p><br/><p>c</p></body></html>')
    ocisti_epub(p)
    t = zipfile.ZipFile(p).read("a.html").decode()
    assert "</p><br/>" not in t
    assert "a<br/>b" in t
    assert ocisti_epub(p)["datoteka"] == 0
