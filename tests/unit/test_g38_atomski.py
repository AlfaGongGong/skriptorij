"""G38: atomic_write_text prima encoding, ne ostavlja .tmp i ne kvari staru datoteku pri padu."""
import pytest
from utils.file_utils import atomic_write_text


def test_encoding_pozicijski_i_kljucni(tmp_path):
    p = tmp_path / "a.txt"
    atomic_write_text(p, "čćž", encoding="utf-8")
    assert p.read_text(encoding="utf-8") == "čćž"
    atomic_write_text(p, "đš", "utf-8")
    assert p.read_text(encoding="utf-8") == "đš"
    assert [x.name for x in tmp_path.iterdir()] == ["a.txt"]


def test_pad_ostavlja_staru(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("staro", encoding="utf-8")
    with pytest.raises(Exception):
        atomic_write_text(p, "novo", encoding="nepostojece-kodiranje")
    assert p.read_text(encoding="utf-8") == "staro"
    assert [x.name for x in tmp_path.iterdir()] == ["b.txt"]
