"""G18: aktivni kod nema tvrdo kodirane /root/skriptorij; putanje dolaze iz config.settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRS = ["core", "processing", "network", "analysis", "epub", "api", "utils"]
IZUZETCI = {"epub/styler_ai.py"}


def _py():
    for d in DIRS:
        for f in (ROOT / d).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if rel not in IZUZETCI:
                yield rel, f
    for n in ("app.py", "main.py", "run.py", "api_fleet.py"):
        if (ROOT / n).exists():
            yield n, ROOT / n


def test_nema_root_skriptorij():
    lose = [rel for rel, f in _py() if "/root/skriptorij" in f.read_text("utf-8", errors="ignore")]
    assert lose == []


def test_nema_books_moonreader_u_stileru_i_kanonu():
    for rel in ("epub/styler.py", "analysis/book_context.py", "core/engine.py"):
        assert "Books/MoonReader" not in (ROOT / rel).read_text("utf-8"), rel


def test_settings_putanje():
    import config.settings as c

    for n in ("KANON_DIR", "KANON_ZRCALO_DIR", "STYLED_DIR", "ORNAMENTS_DIR"):
        assert getattr(c, n).is_absolute(), n
    assert c.CONFIG_PATH.endswith("dev_api.json")


def test_helperi_vracaju_settings():
    import config.settings as c
    from core import engine
    from analysis import book_context
    from processing import pipeline

    assert engine._kanon_dir_cfg() == c.KANON_DIR == book_context._kanon_dir_cfg() == pipeline._kanon_dir_cfg()
    assert engine._kanon_zrcalo_cfg() == c.KANON_ZRCALO_DIR == book_context._kanon_zrcalo_cfg()


def test_styler_koristi_settings():
    import config.settings as c
    import epub.styler as S

    assert S.STYLED_OUTPUT_DIR == str(c.STYLED_DIR)
    assert S.ORNAMENTS_DIR == str(c.ORNAMENTS_DIR)
