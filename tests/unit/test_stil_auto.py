import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core import stil

OPF = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
       '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">%s<dc:title>Neka knjiga</dc:title>'
       '</metadata></package>')

EN = "The old man {n} walked to the market and the dog followed him. He said nothing to the guard."
HR = "Stari čovjek {n} je otišao na tržnicu i pas se poveo za njim. Nije rekao ništa, da se zna."


def _epub(tmp_path, creators, sablona, n=300, ime="t.epub"):
    cr = "".join("<dc:creator>%s</dc:creator>" % c for c in creators)
    ps = "".join("<p>%s</p>" % sablona.format(n=i) for i in range(n))
    p = tmp_path / ime
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/content.opf", OPF % cr)
        z.writestr("OEBPS/c1.xhtml", "<html><body>%s</body></html>" % ps)
    return str(p)


def test_slug_prezime_ime():
    assert stil.slug("Abercrombie, Joe") == stil.slug("Joe Abercrombie") == "joe_abercrombie"


def test_spremi_novi_profil(tmp_path):
    e = _epub(tmp_path, ["Jane Doe"], EN)
    st, p = stil.osiguraj_en_profil(e, root=tmp_path)
    assert st == "spremljeno", st
    assert p.name == "jane_doe.json"
    import json
    prof = json.loads(p.read_text("utf-8"))
    assert prof["jezik"] == "en" and prof["n_recenica"] >= 200


def test_ne_prepisuje_postojeci(tmp_path):
    e = _epub(tmp_path, ["Jane Doe"], EN)
    st, p = stil.osiguraj_en_profil(e, root=tmp_path)
    t0 = p.stat().st_mtime_ns
    st2, p2 = stil.osiguraj_en_profil(e, root=tmp_path)
    assert st2 == "postoji" and p2.stat().st_mtime_ns == t0


def test_preskace_hrvatski(tmp_path):
    e = _epub(tmp_path, ["Jane Doe"], HR)
    assert stil.osiguraj_en_profil(e, root=tmp_path)[0] == "nije_en"


def test_preskace_zbirku(tmp_path):
    e = _epub(tmp_path, ["A One", "B Two", "C Three"], EN)
    assert stil.osiguraj_en_profil(e, root=tmp_path)[0] == "zbirka"


def test_bez_autora(tmp_path):
    e = _epub(tmp_path, [], EN)
    assert stil.osiguraj_en_profil(e, root=tmp_path)[0] == "bez_autora"


def test_losa_datoteka_ne_baca(tmp_path):
    p = tmp_path / "x.epub"
    p.write_bytes(b"nije zip")
    st, _ = stil.osiguraj_en_profil(str(p), root=tmp_path)
    assert st != "spremljeno"


def test_kuka_u_pipelineu():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "processing", "pipeline.py"), encoding="utf-8").read()
    assert "osiguraj_en_profil" in src
