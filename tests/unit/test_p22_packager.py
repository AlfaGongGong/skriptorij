from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "epub" / "packager.py").read_text("utf-8")


def test_packager_nema_sufiksnog_fuzzyja():
    assert "Fuzzy po sufiksu" not in SRC
    assert "P2.2 md5" in SRC
    assert 'suffix = "_".join(parts[i:])' not in SRC
