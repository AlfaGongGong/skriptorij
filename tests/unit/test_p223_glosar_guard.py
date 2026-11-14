from core.oov_kapija import glosar_neprevedeno

G = "- Beauty -> Ljepotica [lik]\n- Beast -> Zvijer [lik]\n- valet -> sobar [termin]\n- Lyon (OSTAVI KAKO JEST, ne prevodi) [lik]\n- Eve -> Eva [lik]"


def test_neprevedeno_nalazi():
    t = "<p>Beautyin otac je rekao da je Beast zao. Valet je otisao.</p>"
    assert glosar_neprevedeno(G, t) == ["Beauty", "Beast", "valet"]


def test_prevedeno_prolazi():
    t = "<p>Ljepoticin otac je rekao da je Zvijer zla. Sobar je otisao. Every Eva Lyon</p>"
    assert glosar_neprevedeno(G, t) == []


def test_prazno():
    assert glosar_neprevedeno("", "x") == [] and glosar_neprevedeno(G, "") == []
