"""G9: _json_upsert i _hr_oznaci ne gube upise kad pise vise niti."""
import json
import threading

from processing import pipeline as P


class _E:
    def __init__(self, d):
        self.checkpoint_dir = d

    def log(self, *a, **k):
        pass


def test_upsert_vise_niti_bez_gubitka(tmp_path):
    e = _E(tmp_path)
    p = tmp_path / "quality_metrics.json"

    def rad(t):
        for i in range(25):
            P._json_upsert(e, p, f"t{t}_b{i}", {"v": i})

    niti = [threading.Thread(target=rad, args=(t,)) for t in range(8)]
    [n.start() for n in niti]
    [n.join() for n in niti]
    d = json.loads(p.read_text("utf-8"))
    assert len(d) == 200
    assert "\n" not in p.read_text("utf-8").strip()


def test_upsert_pokvaren_json_ide_u_bak(tmp_path):
    p = tmp_path / "quality_status.json"
    p.write_text("{pokvareno", "utf-8")
    P._json_upsert(_E(tmp_path), p, "a", 1)
    assert json.loads(p.read_text("utf-8")) == {"a": 1}
    assert (tmp_path / "quality_status.json.bak").exists()


def test_hr_oznaci_vise_niti_i_tip(tmp_path):
    e = _E(tmp_path)

    def rad(t):
        for i in range(10):
            P._hr_oznaci(e, "f", t * 100 + i, "score 5.0 < 6.5", 5.0, "<p>x</p>", "dijalog")

    niti = [threading.Thread(target=rad, args=(t,)) for t in range(6)]
    [n.start() for n in niti]
    [n.join() for n in niti]
    d = json.loads((tmp_path / "human_review.json").read_text("utf-8"))
    assert len(d) == 60 and all(x["tip"] == "dijalog" for x in d)
