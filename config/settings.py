"""Centralne postavke i dijeljeno stanje aplikacije."""

import os
import uuid
from pathlib import Path

# ── Server ────────────────────────────────────────────────────────────────────
PORT: int = int(os.environ.get("SKRIPTORIJ_PORT", 8080))

# Unique ID for this server process — changes on every restart
SERVER_RUN_ID: str = str(uuid.uuid4())

# ── Putanje ───────────────────────────────────────────────────────────────────
PROJECTS_ROOT: str = os.path.join(os.getcwd(), "data")
os.makedirs(PROJECTS_ROOT, exist_ok=True)

CONFIG_PATH: str = os.environ.get("SKRIPTORIJ_CONFIG", "dev_api.json")

# Definisanje putanje za uvoz fajlova
INPUT_DIR: Path = Path("/storage/emulated/0/termux/Skriptorij/data")

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
    "stvarno_prevedeno": 0,
    "spaseno_iz_checkpointa": 0,
}

SHARED_CONTROLS: dict = {
    "pause": False,
    "stop": False,
    "reset": False,
}
