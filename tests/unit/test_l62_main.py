import os
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="treba /proc")


def _cekaj_cmdline(main, pid, znak, sek=5.0):
    """Ceka da /proc/<pid>/cmdline pokaze `znak` (dijete tek exec-a; proot/Android to radi sporo)."""
    kraj = time.time() + sek
    while time.time() < kraj:
        if main._pid_je_nasa(pid, (znak,)) is True:
            return True
        time.sleep(0.05)
    return False


@pytest.fixture()
def tudi_proces():
    import main
    p = subprocess.Popen(["sleep", "30"])
    try:
        if not _cekaj_cmdline(main, p.pid, "sleep"):
            pytest.skip("/proc/<pid>/cmdline nije citljiv u ovom okruzenju")
        yield p
    finally:
        p.kill()
        p.wait()


def test_pid_je_nasa_razlikuje_procese(tudi_proces):
    import main
    p = tudi_proces
    assert main._pid_je_nasa(p.pid) is False
    assert main._pid_je_nasa(p.pid, ("sleep",)) is True
    p.kill()
    p.wait()
    assert main._pid_je_nasa(p.pid) is None


def test_tudi_pid_se_ne_gasi(tudi_proces, tmp_path, monkeypatch):
    import main
    p = tudi_proces
    pidf = tmp_path / "x.pid"
    pidf.write_text(str(p.pid))
    monkeypatch.setattr(main, "_PID_FILE", pidf)
    main._kill_previous_instance()
    assert p.poll() is None, "tudi proces je ugasen"
    assert not pidf.exists()


def test_odluke_kljuc_stabilan():
    from core import odluke
    k = odluke.kljuc("A  b", "C")
    assert k == odluke.kljuc("a b", "c") and len(k) == 16
