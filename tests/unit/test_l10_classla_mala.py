import core.classla_provjera as cp


class _W:
    def __init__(self, t, u):
        self.text, self.upos = t, u


class _S:
    def __init__(self, w):
        self.words = w


class _D:
    def __init__(self, w):
        self.sentences = [_S([_W(t, u) for t, u in w])]


def _an(w, mp):
    doc = _D(w)
    mp.setattr(cp, "_nlp", lambda: (lambda t: doc))
    return cp.analiza("<p>" + " ".join(t for t, _ in w) + " dovoljno dugacak tekst za provjeru</p>")


def test_naslovi_velika_slova_nisu_strani_tekst(monkeypatch):
    w = [("The", "X"), ("Magic", "X"), ("Toyshop", "X"), ("Heroes", "X"), ("and", "X"), ("Villains", "X"),
         ("Mačke", "NOUN"), ("i", "CCONJ"), ("psi", "NOUN"), ("Nocturnes", "X")]
    r = _an(w, monkeypatch)
    assert r["udio_x"] >= 0.3 and r["udio_x_mala"] < 0.2


def test_engleska_proza_ostaje_odbijena(monkeypatch):
    w = [("he", "X"), ("was", "X"), ("older", "X"), ("than", "X"), ("I", "X"), ("Vidjela", "VERB"), ("sam", "AUX")]
    r = _an(w, monkeypatch)
    assert r["udio_x"] >= 0.3 and r["udio_x_mala"] >= 0.2
