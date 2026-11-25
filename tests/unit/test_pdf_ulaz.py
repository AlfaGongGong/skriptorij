"""PDF ulaz: parsiranje pdftotext -layout teksta i izrada EPUB-a."""
import xml.etree.ElementTree as ET
import zipfile

from epub.pdf_ulaz import napravi_epub, parsiraj_sekcije, stranice_iz_layout


def _stranice():
    p1 = "\n".join([
        " " * 21 + "Svetlost sveta teče",
        " " * 21 + "iz svetoga putira",
        "    NE PITAJ ME postoji li Bog, već zašto je takva",
        "čmarina. Ni najveća budaletina ne može da po-",
        "rekne da zlo postoji. Tom & Jerry.",
        "    Drugi odlomak počinje ovdje i",
    ])
    p2 = "\n".join([
        "nastavlja se preko stranice.",
        " " * 37 + "✦ I ✦",
        "",
        " " * 27 + "O IVERJU I KLADAMA",
        "",
        "    BILA JE TO dvadeset sedma godina.",
        "nastavak prvog odlomka.",
        '    „Dijalog“, reče on.',
        " " * 26 + "12",
    ])
    p3 = "KRV I SREBR0"
    p4 = "\n".join([
        " " * 38 + "✦ I ✦",
        "",
        " " * 30 + "DOBAR POČETAK",
        "",
        "    Prvi odlomak trećeg poglavlja.",
    ])
    p5 = "\n".join([
        " " * 30 + "S T R P LJ E NJ E",
        "    Tekst nakon razmaknutog naslova.",
    ])
    return [p1, p2, p3, p4, p5]


def test_stranice_iz_layout():
    assert stranice_iz_layout("a\fb\f") == ["a", "b"]


def test_poglavlja_i_naslovi():
    s = parsiraj_sekcije(_stranice())
    assert [x["naslov"] for x in s] == [
        "Prolog", "O iverju i kladama", "Dobar početak", "Strpljenje"]
    assert [x["broj"] for x in s] == [None, "I", "I", None]
    assert s[2]["dio"] == "Krv i srebro"


def test_odlomci_spajanje():
    s = parsiraj_sekcije(_stranice())
    pro = [v for t, v in s[0]["odlomci"] if t == "p"]
    assert pro[0] == ("Ne pitaj me postoji li Bog, već zašto je takva čmarina. "
                      "Ni najveća budaletina ne može da porekne da zlo postoji. Tom & Jerry.")
    assert pro[1] == "Drugi odlomak počinje ovdje i nastavlja se preko stranice."
    assert s[0]["odlomci"][0][0] == "e"
    gl = [v for t, v in s[1]["odlomci"] if t == "p"]
    assert gl[0] == "Bila je to dvadeset sedma godina. nastavak prvog odlomka."
    assert gl[1] == "„Dijalog“, reče on."
    assert len(gl) == 2  # broj stranice (12) je odbačen


def test_epub_struktura(tmp_path):
    s = parsiraj_sekcije(_stranice())
    out = napravi_epub(s, tmp_path / "k.epub", "Naslov & Co", "Autor", "sr", None, "k")
    z = zipfile.ZipFile(out)
    assert z.namelist()[0] == "mimetype"
    assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    ns = {"o": "http://www.idpf.org/2007/opf"}
    assert len(opf.findall(".//o:spine/o:itemref", ns)) == len(s)
    ET.fromstring(z.read("OEBPS/toc.ncx"))
    ET.fromstring(z.read("META-INF/container.xml"))
    dijelovi = [n for n in z.namelist() if n.endswith(".xhtml")]
    assert len(dijelovi) == len(s)
    for n in dijelovi:
        ET.fromstring(z.read(n))
    assert b"Tom &amp; Jerry" in z.read("OEBPS/part0001.xhtml")


def test_prazno_nije_sekcija():
    assert parsiraj_sekcije(["", "  \n"]) == []
