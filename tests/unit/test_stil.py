# -*- coding: utf-8 -*-
import json
import zipfile

from core import stil


def test_recenice_kratice():
    assert stil._recenice("Mr. Smith went home. He slept.") == ["Mr. Smith went home.", "He slept."]


def test_izmjeri_osnovno():
    odl = ["“Go home,” he said. She did not.", "The night was long and cold.", "“No.”"]
    p = stil.izmjeri(odl, "en")
    assert p["n_recenica"] == 4
    assert p["dijalog_odlomaka_pct"] == 66.7
    assert p["navodnik_pct_dijaloga"] == 100.0


def test_pasiv_en():
    p = stil.izmjeri(["The door was opened by him. He opened the door."], "en")
    assert p["pasiv_pct"] == 50.0


def test_hr_crtica_bez_pasiva_i_fraza():
    p = stil.izmjeri(["— Dobar dan.", "Tekst je ovdje."], "hr")
    assert p["dijalog_odlomaka_pct"] == 50.0
    assert p["crtica_pct_dijaloga"] == 100.0
    assert p["pasiv_pct"] is None
    assert p["fraze"] == []


def test_fraze_en():
    p = stil.izmjeri([" ".join(["He walked down the old road."] * 6)], "en")
    assert any(f == "walked down the" for f, _ in p["fraze"])


def test_prazno():
    p = stil.izmjeri([], "en")
    assert p["n_recenica"] == 0


def _epub(tmp_path):
    put = tmp_path / "t.epub"
    with zipfile.ZipFile(put, "w") as z:
        z.writestr("OEBPS/ch1.xhtml", "<html><body><p>He <i>did</i> go.</p><p>“Hi.”</p></body></html>")
        z.writestr("OEBPS/nav.xhtml", "<html><body><p>skip me</p></body></html>")
    return put


def test_izdvoji_odlomke(tmp_path):
    assert stil.izdvoji_odlomke(_epub(tmp_path)) == ["He did go.", "“Hi.”"]


def test_izmjeri_epube_i_spremi(tmp_path):
    prof = stil.izmjeri_epube([_epub(tmp_path)], "Joe Abercrombie", "en")
    assert prof["autor"] == "Joe Abercrombie" and prof["izvori"][0]["odlomaka"] == 2
    p = stil.spremi(prof, "Joe Abercrombie", "en", root=tmp_path)
    assert p == tmp_path / "data" / "stil" / "joe_abercrombie.json"
    assert json.loads(p.read_text("utf-8"))["n_recenica"] == prof["n_recenica"]
    assert stil.spremi(prof, "Joe Abercrombie", "hr", root=tmp_path).name == "joe_abercrombie_hr.json"


def test_slug():
    assert stil.slug("Žarko Čović") == "zarko_covic"
    assert stil.slug("") == "nepoznat_autor"


# ── P4.3: usporedi() i kapija ────────────────────────────────────────────────
def test_usporedi_u_granicama():
    en = {"n_recenica": 1000, "prosj_rijeci_po_recenici": 9.9, "dijalog_odlomaka_pct": 55.8}
    hr = {"n_recenica": 900, "prosj_rijeci_po_recenici": 9.3, "dijalog_odlomaka_pct": 56.4,
          "crtica_pct_dijaloga": 100.0}
    assert stil.usporedi(en, hr) == []


def test_usporedi_duga_recenica():
    en = {"n_recenica": 1000, "prosj_rijeci_po_recenici": 9.9, "dijalog_odlomaka_pct": 55.8}
    hr = {"n_recenica": 900, "prosj_rijeci_po_recenici": 14.0, "dijalog_odlomaka_pct": 56.0,
          "crtica_pct_dijaloga": 100.0}
    r = stil.usporedi(en, hr)
    assert len(r) == 1 and r[0][0].startswith("stil: duzina")


def test_usporedi_dijalog_i_crtica():
    en = {"n_recenica": 1000, "prosj_rijeci_po_recenici": 9.9, "dijalog_odlomaka_pct": 55.8}
    hr = {"n_recenica": 900, "prosj_rijeci_po_recenici": 9.5, "dijalog_odlomaka_pct": 20.0,
          "crtica_pct_dijaloga": 10.0}
    imena = [c for c, _ in stil.usporedi(en, hr)]
    assert len(imena) == 2
    assert any(c.startswith("stil: udio dijaloga") for c in imena)
    assert any(c.startswith("stil: HR dijalog bez crtica") for c in imena)


def test_usporedi_premalo_uzorka():
    en = {"n_recenica": 1000, "prosj_rijeci_po_recenici": 9.9, "dijalog_odlomaka_pct": 55.8}
    hr = {"n_recenica": 50, "prosj_rijeci_po_recenici": 30.0, "dijalog_odlomaka_pct": 0.0}
    assert stil.usporedi(en, hr) == []


def _hr_epub(tmp_path, n=250):
    rec = "Ovo je jedna prilično dugačka rečenica koja ima točno dvanaest riječi ovdje."
    put = tmp_path / "hr.epub"
    container = ('<?xml version="1.0"?><container version="1.0" '
                 'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    opf = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:title>T</dc:title><dc:language>hr</dc:language><dc:creator>Joe Abercrombie</dc:creator>'
           '<dc:identifier id="id">x</dc:identifier></metadata><manifest>'
           '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
           '<spine><itemref idref="c1"/></spine></package>')
    nav = '<html xmlns="http://www.w3.org/1999/xhtml"><body><nav><a href="ch1.xhtml">1</a></nav></body></html>'
    ch1 = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>'
           + "".join("<p>%s</p>" % rec for _ in range(n)) + "</body></html>")
    with zipfile.ZipFile(put, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/ch1.xhtml", ch1)
    return put


def test_gate_stil_warn_i_iskljucen(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import epub_gate

    en = {"jezik": "en", "n_recenica": 1000, "prosj_rijeci_po_recenici": 5.0, "dijalog_odlomaka_pct": 50.0}
    put = str(_hr_epub(tmp_path))
    ok, rep = epub_gate.gate(put, stil=en)
    imena = [r[1] for r in rep]
    assert any(c.startswith("stil: duzina") for c in imena)
    assert any(c.startswith("stil: udio dijaloga") for c in imena)
    assert all(r[0] == "WARN" for r in rep if r[1].startswith("stil:"))
    ok2, rep2 = epub_gate.gate(put, stil=False)
    assert not any(r[1].startswith("stil:") for r in rep2)
    assert ok == ok2
