import re
from pathlib import Path

MARKER = r"Let's|\" ->|\(Wait|\bwe need to\b"


def _src():
    return Path(__file__).resolve().parents[2].joinpath("processing", "verifier_hook.py").read_text(encoding="utf-8")


def test_raw_tail_u_zapisu_sumnjive_duljine():
    s = _src()
    assert "raw_pocetak=raw[:200]" in s
    assert "raw_kraj=raw[-200:]" in s
    assert "raw_duljina=len(raw)" in s
    assert "curenje=bool(" in s


def test_marker_je_isti_u_kodu_i_testu():
    assert MARKER in _src()


def test_marker_hvata_poznati_potpis_curenja():
    rx = re.compile(MARKER)
    assert rx.search("Let's refine vocabulary: dano u zamjenu")
    assert rx.search('(Wait: "nismo ih razumjeli" -> "nismo ih razumjela")')
    assert not rx.search("Uobicajen hrvatski prijevod bez ikakvih oznaka razmisljanja.")
