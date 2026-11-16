from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _css():
    return (ROOT / "static" / "css" / "design.css").read_text(encoding="utf-8")


def test_r6_blok_prisutan_i_na_kraju():
    s = _css()
    assert "/* R6:" in s
    assert s.rfind("/* R6:") > s.rfind("/* R5")  # nakon R5 bloka


def test_r6_pravila():
    s = _css().split("/* R6:", 1)[1]
    assert ":focus-visible" in s
    assert "(pointer: coarse)" in s and "min-height: 44px" in s
    assert "prefers-reduced-motion: reduce" in s
    assert "forced-colors: active" in s


def test_index_ima_novi_v_za_design_css():
    s = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "static/css/design.css?v=" in s
