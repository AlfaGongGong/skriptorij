"""G17: V2 put (WorkerV2) je zadano ISKLJUCEN; BOOKLYFI_V2=1 ga ukljucuje."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KOD = "import processing.pipeline as P; print(int(bool(P.USE_WORKERS_V2)), int(bool(P._V2_DOSTUPAN)))"


def _pokreni(v2):
    env = {k: v for k, v in os.environ.items() if k != "BOOKLYFI_V2"}
    if v2 is not None:
        env["BOOKLYFI_V2"] = v2
    r = subprocess.run(
        [sys.executable, "-c", KOD], cwd=str(ROOT), env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout.strip().split()[-2:]


def test_v2_zadano_iskljucen():
    uk, _ = _pokreni(None)
    assert uk == "0"


def test_v2_ukljucuje_se_env_om():
    uk, dostupan = _pokreni("1")
    if dostupan != "1":
        return
    assert uk == "1"
