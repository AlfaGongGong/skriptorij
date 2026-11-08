import zipfile

from core import autor_analiza as AA
from core import zbirka as ZB


def _epub(tmp_path, ime, autori, naslov):
    p = tmp_path / ime
    kr = "".join(f"<dc:creator>{a}</dc:creator>" for a in autori)
    opf = ('<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f"<metadata><dc:title>{naslov}</dc:title>{kr}</metadata></package>")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("content.opf", opf)
    return p


def test_vise_autora_je_zbirka(tmp_path):
    ok, razlog = ZB.je_zbirka(_epub(tmp_path, "x.epub", ["A", "B", "C"], "Nesto"))
    assert ok and "autora" in razlog


def test_jedan_autor_nije_zbirka(tmp_path):
    assert ZB.je_zbirka(_epub(tmp_path, "roman.epub", ["Stephen King"], "A Death")) == (False, "")


def test_rijec_u_naslovu(tmp_path):
    assert ZB.je_zbirka(_epub(tmp_path, "k.epub", ["Urednik"], "Best of Fantasy"))[0]


def test_rucna_lista_unbound_jedan_urednik(tmp_path):
    assert ZB.je_zbirka(_epub(tmp_path, "Shawn_Speakman_Unbound.epub", ["Shawn Speakman"], "Unbound"))[0]


def test_nepostojeci_fajl_ne_ruši(tmp_path):
    assert ZB.je_zbirka(tmp_path / "nema.epub")[0] is False


def test_hook_zbirka_vraca_gresku_a_roman_delegira(monkeypatch, tmp_path):
    monkeypatch.setattr(AA, "_analiziraj_knjigu_orig", lambda p, m=30000: {"stil": "x"})
    zb = _epub(tmp_path, "z.epub", ["A", "B", "C"], "Nesto")
    assert AA.analiziraj_knjigu(str(zb)).get("greska", "").startswith("zbirka")
    jedan = _epub(tmp_path, "j.epub", ["A"], "Roman")
    assert AA.analiziraj_knjigu(str(jedan)) == {"stil": "x"}
