"""G8: prompt vise ne uci model da ublazava ('ne ublažavaj' + eufemizam bili su kontradiktorni)."""
from pathlib import Path


def test_nema_eufemizma_u_promptu():
    t = (Path(__file__).resolve().parents[2] / "core" / "prompts.py").read_text(encoding="utf-8")
    assert "silovao je beživotno tijelo" not in t
    assert "ne ublažavaj" in t
    assert "bez eufemizma" in t
