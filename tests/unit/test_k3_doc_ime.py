from pathlib import Path
R = Path(__file__).resolve().parents[2]


def _ime(blok):
    return blok.rsplit("_blok_", 1)[0] if "_blok_" in blok else blok.split(".html_blok")[0] + ".html"


def test_ime_dokumenta():
    assert _ime("part0007.html_blok_2") == "part0007.html"
    assert _ime("x.xhtml_blok_12") == "x.xhtml"
    assert _ime("a.html_blok0003") == "a.html"


def test_izvori_koriste_rsplit():
    for f in ("api/routes/processing.py", "core/sidro.py", "tools/arbitar_run.py"):
        assert 'rsplit("_blok_", 1)' in (R / f).read_text(encoding="utf-8")
