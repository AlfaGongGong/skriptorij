import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core import stil


def _epub(tmp_path, html):
    p = tmp_path / "t.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/chapter1.xhtml", html)
    return str(p)


def test_goli_tekst_u_body_s_br(tmp_path):
    html = ("<html><head><title>Naslov knjige</title></head><body>"
            "Prvi redak ovdje.<br/>Drugi redak tu.<p>Treci odlomak.</p></body></html>")
    odl = stil.izdvoji_odlomke(_epub(tmp_path, html))
    assert "Prvi redak ovdje." in odl
    assert "Drugi redak tu." in odl
    assert "Treci odlomak." in odl
    assert not any("Naslov knjige" in o for o in odl)
    assert len(odl) == 3


def test_samo_p_nepromijenjeno(tmp_path):
    html = "<html><body><p>Jedan.</p><p>Dva.</p></body></html>"
    assert stil.izdvoji_odlomke(_epub(tmp_path, html)) == ["Jedan.", "Dva."]


def test_goli_tekst_u_blockquote(tmp_path):
    html = "<html><body><blockquote>Epigraf bez p oznake.</blockquote></body></html>"
    assert stil.izdvoji_odlomke(_epub(tmp_path, html)) == ["Epigraf bez p oznake."]


def test_komentar_i_razmaci_ne_ulaze(tmp_path):
    html = "<html><body>\n  <!-- komentar -->\n  <p>Samo ovo.</p>\n</body></html>"
    assert stil.izdvoji_odlomke(_epub(tmp_path, html)) == ["Samo ovo."]
