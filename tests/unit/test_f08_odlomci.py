import asyncio

import pytest

from processing import pipeline as P


class Fake:
    def __init__(self, odgovori):
        self.odgovori = list(odgovori)
        self.pozivi = []

    def log(self, *a, **k):
        pass

    async def _call_ai_engine(self, prompt, idx, **kw):
        self.pozivi.append(prompt)
        return self.odgovori.pop(0)


@pytest.fixture(autouse=True)
def _bez_extracta(monkeypatch):
    monkeypatch.setattr(P, "_smart_extract", lambda r: r)


def _run(f, chunk):
    return asyncio.run(P._posalji_po_paragrafima(f, chunk, 1, "k.xhtml", "sys", "tip"))


CHUNK = "<h2>Title</h2><p>One.</p><ul><li>a</li><li>b</li></ul><p>Two.</p>"


def test_cuva_naslove_liste_redoslijed_bez_dvostrukog_p():
    f = Fake(
        [
            ("<h2>Naslov</h2>", "G"),
            ("Jedan.", "G"),
            ("<ul><li>a1</li><li>b1</li></ul>", "G"),
            ("<p>Dva.</p>", "G"),
        ]
    )
    out, mark = _run(f, CHUNK)
    assert mark == 0
    assert out.find("Naslov") < out.find("Jedan") < out.find("a1") < out.find("Dva")
    assert "<h2>Naslov</h2>" in out and "<ul>" in out
    assert "<p><p>" not in out
    assert out.count("<p>Dva.</p>") == 1
    assert "<p>Jedan.</p>" in out


def test_stvarni_filter_daje_marker_a_naslov_ostaje():
    f = Fake([("<h2>Naslov</h2>", "G"), (None, "CONTENT_FILTER"), ("<ul><li>x</li></ul>", "G"), ("Dva.", "G")])
    out, mark = _run(f, CHUNK)
    assert mark == 1
    assert "[[MANUAL: chunk 1, dio 2]]" in out
    assert "Naslov" in out and "<li>x</li>" in out


def test_mrezna_greska_prekida_bez_manual():
    f = Fake([("<h2>Naslov</h2>", "G"), (None, "ALL_FAILED")])
    out, mark = _run(f, CHUNK)
    assert out is None and mark == -1


def test_cisti_tekst_bez_tagova():
    f = Fake([("Prijevod.", "G")])
    out, mark = _run(f, "A b. C d. E f.")
    assert out == "Prijevod." and mark == 0


def test_korektor_se_preskace_za_auto_hr():
    src = open(P.__file__, encoding="utf-8").read()
    assert 'if prov_l == "AUTO-HR" else await self._call_ai_engine(' in src
