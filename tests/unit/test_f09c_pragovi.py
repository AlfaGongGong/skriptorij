import json
import pathlib
import types

import pytest

from core import quality, skip_oracle

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_scorer_override_nema_marker():
    fleet = types.SimpleNamespace(keys=lambda: ["gemini", "groq"])
    obj = types.SimpleNamespace(fleet=fleet)
    assert quality.get_scorer_sys_override(obj, "gemini", 0, "t.xhtml") is None
    tekst = (ROOT / "core" / "quality.py").read_text("utf-8")
    assert "__FORCE_PROVIDER__" not in tekst


def test_report_koristi_stvarne_pragove(tmp_path):
    cdir = tmp_path / "checkpoints"
    cdir.mkdir()
    ocjene = {"a": 9.0, "b": 8.7, "c": 8.5, "d": 8.2, "e": 8.0, "f": 7.9, "g": 5.0}
    (cdir / "quality_scores.json").write_text(json.dumps(ocjene), "utf-8")
    r = quality.generiraj_report("knjiga", checkpoint_dir=str(cdir))
    assert (r["iz_prve"], r["retry"], r["karantena"]) == (3, 2, 2)
    assert r["proc_iz_prve"] == 42.9


def test_pragovi_jedna_tablica():
    assert skip_oracle.MIN_SCORE_ZA_SKIP == quality._QUALITY_EXCELLENT_THRESHOLD
    assert quality._HR_REVIEW_THRESHOLD == 6.5


def test_pipeline_bez_brojke_6_5():
    tekst = (ROOT / "processing" / "pipeline.py").read_text("utf-8")
    if "_HR_REVIEW_THRESHOLD" not in tekst:
        pytest.skip("pipeline nije mijenjan")
    assert "score_float < 6.5" not in tekst
