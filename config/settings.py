"""Centralne postavke i dijeljeno stanje aplikacije."""

import os
import uuid
from pathlib import Path

# ── Server ────────────────────────────────────────────────────────────────────
PORT: int = int(os.environ.get("SKRIPTORIJ_PORT", 8080))

# Unique ID for this server process — changes on every restart
SERVER_RUN_ID: str = str(uuid.uuid4())

# ── Korijenski direktorij projekta (apsolutno, uvijek tačno bez obzira na cwd) ──
# __file__ je config/settings.py → .parent je config/ → .parent je root projekta
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ── Putanje ──────────────────────────────────────────────────────────────────

# Ulazni direktorij za knjige koje čekaju prijevod
INPUT_DIR: Path = Path(
    os.environ.get(
        "SKRIPTORIJ_INPUT_DIR",
        os.path.join(os.path.expanduser("~"), "Skriptorij", "data"),
    )
)
os.makedirs(INPUT_DIR, exist_ok=True)

# Izlazni direktorij — Moon+ Reader biblioteka na Androidu.
_DEFAULT_OUTPUT = "/storage/emulated/0/Books/MoonReader/booklyfi"
OUTPUT_DIR: Path = Path(os.environ.get("SKRIPTORIJ_OUTPUT_DIR", _DEFAULT_OUTPUT))

try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
except OSError:
    OUTPUT_DIR = INPUT_DIR

# ── Checkpoint putanje ────────────────────────────────────────────────────────
_ANDROID_CHECKPOINT_DIR = Path("/storage/emulated/0/booklyfi_checkpoints")
_LOCAL_CHECKPOINT_DIR = INPUT_DIR / "_checkpoints"


def _resolve_checkpoint_base() -> Path:
    """Pokušava koristiti Android storage, pada na lokalnu putanju."""
    try:
        _ANDROID_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        test = _ANDROID_CHECKPOINT_DIR / ".write_test"
        test.touch()
        test.unlink()
        return _ANDROID_CHECKPOINT_DIR
    except OSError:
        _LOCAL_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        return _LOCAL_CHECKPOINT_DIR


CHECKPOINT_BASE_DIR: Path = _resolve_checkpoint_base()

# ── FIX: CONFIG_PATH mora biti apsolutna putanja ──────────────────────────────
# Staro: CONFIG_PATH = os.environ.get("SKRIPTORIJ_CONFIG", "dev_api.json")
# Problem: relativna putanja "dev_api.json" se rješava od cwd(), a ne od
#          mjesta gdje je projekat. Kad Termux pokrene app iz drugog direktorija,
#          FleetManager tiho ne učita ni jedan ključ → "Nema provajdera u floti."
# Ispravno: uvijek koristiti apsolutnu putanju relativnu od korijena projekta.
CONFIG_PATH: str = os.environ.get(
    "SKRIPTORIJ_CONFIG",
    str(_PROJECT_ROOT / "dev_api.json"),  # ← apsolutna putanja
)

# Ime projekta (koristi se u logovima i imenima direktorija)
PROJECTS_ROOT: Path = INPUT_DIR

# ── Dijeljeno stanje (zajednički rječnik između Flask threada i processing threada) ─
SHARED_STATS: dict = {
    "status": "IDLE",
    "active_engine": "---",
    "current_file": "---",
    "current_file_idx": 0,
    "total_files": 0,
    "current_chunk_idx": 0,
    "total_file_chunks": 0,
    "ok": "0 / 0",
    "skipped": "0",
    "pct": 0,
    "est": "--:--:--",
    "fleet_active": 0,
    "fleet_cooling": 0,
    "live_audit": "Sistem spreman. Čekam inicijalizaciju...",
    "output_file": "",
    "output_dir": str(OUTPUT_DIR),
    "stvarno_prevedeno": 0,
    "spaseno_iz_checkpointa": 0,
    "quality_scores": {},
    "glosar_problemi": {},
    "knjiga_mode": None,
    "knjiga_mode_info": "",
}

SHARED_CONTROLS: dict = {
    "pause": False,
    "stop": False,
    "reset": False,
}
