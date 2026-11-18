import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="treba /proc")


def test_pid_je_nasa_razlikuje_procese():
    import main
    p = subprocess.Popen(["sleep", "30"])
    try:
        assert main._pid_je_nasa(p.pid) is False
        assert main._pid_je_nasa(p.pid, ("sleep",)) is True
    finally:
        p.kill()
        p.wait()
    assert main._pid_je_nasa(p.pid) is None


def test_tudi_pid_se_ne_gasi(tmp_path, monkeypatch):
    import main
    pidf = tmp_path / "x.pid"
    p = subprocess.Popen(["sleep", "30"])
    try:
        pidf.write_text(str(p.pid))
        monkeypatch.setattr(main, "_PID_FILE", pidf)
        main._kill_previous_instance()
        assert p.poll() is None, "tudi proces je ugasen"
        assert not pidf.exists()
    finally:
        p.kill()
        p.wait()


def test_odluke_kljuc_stabilan():
    from core import odluke
    k = odluke.kljuc("A  b", "C")
    assert k == odluke.kljuc("a b", "c") and len(k) == 16
