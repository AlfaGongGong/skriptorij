from pathlib import Path


def test_fab_u_index_html():
    s = (Path(__file__).resolve().parent.parent / "templates" / "index.html").read_text("utf-8")
    assert s.count('id="p26-revizija-fab"') == 1
    assert s.count('href="/revizija"') >= 2  # gumb u Rev. tabu + plutajuci
    assert s.count("</body>") == 1 and s.index("p26-revizija-fab") < s.index("</body>")
