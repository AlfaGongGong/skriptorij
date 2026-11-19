from pathlib import Path

from epub.styler import _skr_po_pokrivenosti, _skr_pokrivenost


def _mk(base, ime, blokovi):
    ck = base / ime / "checkpoints"
    ck.mkdir(parents=True)
    for b in blokovi:
        (ck / (b + "_blok_0.chk")).write_text("<p>x</p>", "utf-8")
        (ck / (b + "_blok_0.lektura.chk")).write_text("<p>x</p>", "utf-8")
    return base / ime


def test_bira_mapu_s_najvise_pokrivenih_dokumenata(tmp_path):
    stara = _mk(tmp_path, "_skr_Stara", ["booklyfi_001_naslovna.xhtml", "part0001.xhtml"])
    prava = _mk(tmp_path, "_skr_Prava", ["part%04d.xhtml" % i for i in range(1, 11)])
    imena = ["OEBPS/Text/part%04d.xhtml" % i for i in range(1, 11)]
    mapa, n = _skr_po_pokrivenosti([stara, prava], imena)
    assert mapa == prava and n == 10
    assert _skr_pokrivenost(stara, imena) == 1


def test_nema_pokrivenosti_ili_neodluceno(tmp_path):
    a = _mk(tmp_path, "_skr_A", ["part0001.xhtml"])
    b = _mk(tmp_path, "_skr_B", ["part0001.xhtml"])
    assert _skr_po_pokrivenosti([a, b], ["Text/part0001.xhtml"])[0] is None
    assert _skr_po_pokrivenosti([a], ["Text/drugo.xhtml"]) == (None, 0)
