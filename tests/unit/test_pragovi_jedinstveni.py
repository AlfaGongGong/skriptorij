import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import quality as Q
from processing import retro as R

W = (Path(__file__).resolve().parents[2] / "processing" / "workers.py").read_text("utf-8")


def test_retro_prag_vezan():
    assert R._RETRO_QA_THRESHOLD == Q._QUALITY_RESCUE_THRESHOLD == 8.0


def test_workers_nema_tvrdog_9_5():
    assert "ukupno < 9.5" not in W and "novi_ocjena >= 9.5" not in W
    assert "_QUALITY_RESCUE_THRESHOLD" in W
