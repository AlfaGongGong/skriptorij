from pathlib import Path
R = Path(__file__).resolve().parents[2]


def test_views_guard_active_tab():
    s = (R / "static/js/ui/views.js").read_text(encoding="utf-8")
    assert "prevActive" in s and "if (t === prevActive) return;" in s


def test_zen_toggle_removed():
    s = (R / "static/js/main.js").read_text(encoding="utf-8")
    assert "zen-toggle-btn" not in s
