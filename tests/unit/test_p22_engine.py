from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "core" / "engine.py").read_text("utf-8")


def test_engine_prihvaca_html_u_korijenu():
    assert "P2.2 html u korijenu" in SRC
    assert SRC.count('any(k.glob("*.*html"))') == 2
