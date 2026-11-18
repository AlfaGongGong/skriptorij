import ast
import pathlib
import zipfile

from core import zbirka as ZB

KORIJEN = pathlib.Path(__file__).resolve().parents[2]


def test_styler_nema_golih_except():
    src = (KORIJEN / "epub" / "styler.py").read_text(encoding="utf-8")
    gole = [n.lineno for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.ExceptHandler) and n.type is None]
    assert gole == []


def test_zbirka_odbija_opf_s_entitetima(tmp_path):
    p = tmp_path / "x.epub"
    opf = ('<?xml version="1.0"?><!DOCTYPE package [<!ENTITY a "b">]>'
           '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<metadata><dc:title>Nesto</dc:title><dc:creator>A</dc:creator>'
           '<dc:creator>B</dc:creator><dc:creator>C</dc:creator></metadata></package>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("content.opf", opf)
    assert ZB.je_zbirka(p) == (False, "")
