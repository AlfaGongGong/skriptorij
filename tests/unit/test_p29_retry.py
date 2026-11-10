import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from processing import parallel as P


class _Fleet:
    def get_total_active_keys(self):
        return 2


class _Eng:
    def __init__(self, ishodi):
        self.fleet = _Fleet()
        self.ishodi = list(ishodi)
        self.poziva = 0
        self.checkpoint_dir = Path("/nepostojeci")
        self.shared_stats = {}

    def log(self, *a, **k):
        pass

    async def process_chunk_with_ai(self, chunk, p, n, idx, fn):
        self.poziva += 1
        r = self.ishodi.pop(0) if self.ishodi else "ok"
        return (None, "TRUNCATED") if r is None else (r, "T")


def _run(ishodi):
    P._RETRY_PAUZA = 0
    e = _Eng(ishodi)
    ap = P.AdaptiveParallelism(e)
    ap._human_delay = (0, 0)
    res = asyncio.run(ap.process_chunks_parallel(["x"], "f.html", lambda c, i: "", lambda c, i: ""))
    return e, res


def test_ponovi_pa_uspije():
    e, res = _run([None, None, "tekst"])
    assert e.poziva == 3 and res[0][0] == "tekst"


def test_odustane_nakon_limita():
    e, res = _run([None] * 10)
    assert e.poziva == 1 + P._MAX_PONOVNIH and res[0][0] is None


def test_workers_en_guard():
    src = (Path(__file__).resolve().parents[2] / "processing" / "workers.py").read_text("utf-8")
    assert "_detektuj_en_ostatke(_fb_txt) < 0.08" in src
