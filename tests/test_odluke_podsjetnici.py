from pathlib import Path

import pytest

from core import odluke


@pytest.fixture(autouse=True)
def izolacija(tmp_path, monkeypatch):
    monkeypatch.setattr(odluke, "PUTANJA", tmp_path / "odluke.jsonl")


def _z(en, hr, novo, odluka="prevedi_ponovo", knjiga="K", blok="p.html_blok_0"):
    odluke.zabiljezi(knjiga, blok, en, hr, "broj", odluka, novo)


def test_nalazi_fragment_u_html_i_normalizira():
    _z("quarter past eleven", "petnaest do jedanaest", "jedanaest i petnaest")
    p = odluke.podsjetnici('<p>It was  Quarter\nPast Eleven when he left.</p>')
    assert [x["novo"] for x in p] == ["jedanaest i petnaest"]
    assert "jedanaest i petnaest" in odluke.formatiraj_podsjetnike("at quarter past eleven")


def test_apostrof_normalizacija():
    _z("he didn't finish by sunup", "nije", "nije stigao")
    assert odluke.podsjetnici("he didn\u2019t finish by sunup, so")


def test_ignorira_kratke_nepovezane_i_nenovo():
    _z("past", "a", "b")                              # prekratak EN
    _z("quarter past eleven", "x", "x")               # hr == novo
    _z("quarter past eleven", "x", "")                # bez novog
    _z("some other phrase here", "x", "y", odluka="ostavi")
    assert odluke.podsjetnici("quarter past eleven some other phrase here") == []
    assert odluke.formatiraj_podsjetnike("") == ""


def test_ne_pojavljuje_se_u_bloku():
    _z("quarter past eleven", "x", "y")
    assert odluke.podsjetnici("completely different text") == []


def test_dedupe_ponisti_i_max_n():
    _z("alpha beta gamma delta", "a", "b")
    _z("alpha beta gamma delta", "a", "b", knjiga="K2")   # isti par u drugoj knjizi
    for i in range(5):
        _z(f"unique phrase number {i}", "a", f"n{i}")
    txt = "alpha beta gamma delta " + " ".join(f"unique phrase number {i}" for i in range(5))
    p = odluke.podsjetnici(txt, max_n=3)
    assert len(p) == 3 and len({x["en"] for x in p}) == 3
    odluke.zabiljezi("K", "p.html_blok_0", "unique phrase number 4", "a", "broj", "ponisti", "")
    assert all(x["en"] != "unique phrase number 4" for x in odluke.podsjetnici(txt, max_n=10))


def test_pipeline_hook_jednom_i_prije_p_fusion():
    s = (Path(__file__).resolve().parent.parent / "processing" / "pipeline.py").read_text("utf-8")
    assert s.count("formatiraj_podsjetnike(chunk)") == 1
    assert s.index("formatiraj_podsjetnike(chunk)") < s.index('p_fusion = f"Engleski tekst za prevod:')
