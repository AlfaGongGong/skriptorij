"""L50-2: styler (popravak navodnika pa tipografija) ne vraca navodnike oko replike."""
import pytest
from bs4 import BeautifulSoup


def test_styler_redoslijed_ostavlja_crticu():
    import core.tipografija as tip
    if not hasattr(tip, "_replike_u_crtice"):
        pytest.skip("nema _replike_u_crtice")
    from epub.styler import _navodnici_popravi
    soup = BeautifulSoup("<p>\u201eDo\u0111i ovamo!\u201d viknu on.</p>", "html.parser")
    _navodnici_popravi(soup)
    tip.normaliziraj_soup(soup)
    t = soup.get_text().lstrip()
    assert t.startswith("\u2014"), t
    assert "\u201e" not in t, t
