"""
tests/golden/test_styler.py
Golden test za epub/styler.py — deterministicka provera nad mini EPUB-om.
Ne menja izvor, pise u tmp dir.
"""

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

FIXTURE = Path(__file__).parent / "fixtures" / "mini_hatred.epub"


@pytest.mark.skipif(not FIXTURE.exists(), reason="Mini EPUB fixture nedostaje")
def test_styler_run_on_mini_epub(tmp_path):
    """run_epub_styler mora da vrati ok=True, ima chapters>0, toc_created=True."""
    from epub.styler import run_epub_styler

    out = tmp_path / "out.epub"
    res = run_epub_styler(str(FIXTURE), output_path=str(out))

    assert res.get("ok") is True, f"styler pao: {res.get('error')}"
    assert res.get("chapters", 0) > 0, f"nema chapters: {res}"
    assert res.get("dropcaps_added", 0) > 0, f"nema dropcaps: {res}"
    assert res.get("toc_created") is True, f"TOC nije kreiran: {res}"
    assert out.exists(), "output EPUB nije kreiran"
    assert out.stat().st_size > 0, "output EPUB je prazan"


@pytest.mark.skipif(not FIXTURE.exists(), reason="Mini EPUB fixture nedostaje")
def test_styler_output_is_valid_epub(tmp_path):
    """Output mora biti validan ZIP, imati booklyfi stranice, NCX navPoints, XML validan."""
    from epub.styler import run_epub_styler

    out = tmp_path / "out.epub"
    res = run_epub_styler(str(FIXTURE), output_path=str(out))
    assert res.get("ok") is True

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        xhtml = [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]

        # Booklyfi stranice
        assert any("booklyfi_001_naslovna" in n for n in xhtml), "nema naslovnu"
        assert any("booklyfi_002_impresum" in n for n in xhtml), "nema impresum"

        # NCX
        ncx = [n for n in names if n.endswith(".ncx")]
        assert ncx, "nema NCX"
        ncx_content = z.read(ncx[0]).decode("utf-8", errors="replace")
        import re

        navpoints = len(re.findall(r"<navPoint", ncx_content))
        assert navpoints > 0, "NCX ima 0 navPoints"

        # XML validnost za sve XHTML
        errors = []
        for n in xhtml:
            try:
                ET.fromstring(z.read(n))
            except Exception as e:
                errors.append((n, str(e)[:100]))
        assert not errors, f"XML greske: {errors[:3]}"


@pytest.mark.skipif(not FIXTURE.exists(), reason="Mini EPUB fixture nedostaje")
def test_styler_output_has_nav_in_spine(tmp_path):
    """nav.xhtml mora biti u OPF spine (iza impresum, prije poglavlja)."""
    from epub.styler import run_epub_styler

    out = tmp_path / "out.epub"
    res = run_epub_styler(str(FIXTURE), output_path=str(out))
    assert res.get("ok") is True

    with zipfile.ZipFile(out) as z:
        opfs = [n for n in z.namelist() if n.endswith(".opf")]
        assert opfs
        opf_content = z.read(opfs[0]).decode("utf-8", errors="replace")
        import re as _re

        _v = _re.search(r'<package[^>]*\sversion="([^"]+)"', opf_content)
        if _v and _v.group(1).startswith("2"):
            assert 'idref="nav"' not in opf_content, "EPUB 2: nav ne smije biti u spine"
            assert 'properties="nav"' not in opf_content, "EPUB 2: nav item ne smije postojati"
        else:
            assert 'idref="nav"' in opf_content, "nav nije u spine"
