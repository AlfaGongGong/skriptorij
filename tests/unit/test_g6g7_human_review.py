"""G6+G7: human_review.json dobiva PREVOD-FALLBACK, NEPREVEDENO i blokove prihvacene kapijom (fail-open)."""
import json

from processing import pipeline as P


class _E:
    def __init__(self, d):
        self.checkpoint_dir = d
        self.logs = []

    def log(self, m, l="info"):
        self.logs.append(m)


def _citaj(d):
    return json.loads((d / "human_review.json").read_text("utf-8"))


def test_zapis_i_spajanje_razloga(tmp_path):
    e = _E(tmp_path)
    P._hr_oznaci(e, "f", 3, "neprevedeno", 1.0, "<p>Abc</p>")
    P._hr_oznaci(e, "f", 3, "neprevedeno", 1.0)
    P._hr_oznaci(e, "f", 3, "drugi")
    d = _citaj(tmp_path)
    assert len(d) == 1
    assert d[0]["stem"] == "f_blok_3" and d[0]["reason"] == "neprevedeno; drugi" and d[0]["preview"] == "Abc"


def test_postojeci_zapis_ostaje(tmp_path):
    (tmp_path / "human_review.json").write_text(json.dumps([{"stem": "x_blok_1", "score": 5.0, "tip": "t", "preview": "p"}]), "utf-8")
    P._hr_oznaci(_E(tmp_path), "f", 2, "r")
    d = _citaj(tmp_path)
    assert [i["stem"] for i in d] == ["x_blok_1", "f_blok_2"]


def test_kapija_failopen_upisuje_tek_treci_put(tmp_path):
    e = _E(tmp_path)
    assert P._kapija_odbij(e, "f", 1) is True
    assert P._kapija_odbij(e, "f", 1) is True
    assert not (tmp_path / "human_review.json").exists()
    assert P._kapija_odbij(e, "f", 1) is False
    assert "kapija" in _citaj(tmp_path)[0]["reason"]


def test_pokvaren_json_se_sprema_u_bak(tmp_path):
    (tmp_path / "human_review.json").write_text("{pokvareno", "utf-8")
    P._hr_oznaci(_E(tmp_path), "f", 1, "r")
    assert (tmp_path / "human_review.json.bak").exists()
    assert len(_citaj(tmp_path)) == 1
