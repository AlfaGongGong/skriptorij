from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "processing" / "workers.py").read_text("utf-8")


def test_marker_put_pise_chk_i_koristi_prevod_fallback():
    assert "P2.9 marker put" in SRC
    assert ".prevod.chk" in SRC
    assert "_cw_mk(self, file_name, i, _marker" in SRC
    assert "_hl_mk" not in SRC
