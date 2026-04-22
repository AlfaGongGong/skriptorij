"""
Rute za upravljanje obradom knjiga (files, start, status, modeli).
Dio Skriptorij V10 Turbo Omni-Core sistema.
"""

import json
import os
import threading
import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

# Uvozimo globalne konstante - OSIGURAJ DA JE INPUT_DIR DEFINISAN U config/settings.py
from config.settings import (
    PROJECTS_ROOT,
    SHARED_STATS,
    SHARED_CONTROLS,
    CONFIG_PATH,
    INPUT_DIR,
)
from utils.file_utils import secure_filename, safe_path

bp = Blueprint("processing", __name__)

# Globalno praćenje vremena za ETA računanje
_start_time: float | None = None
_start_pct: float = 0

# ============================================================================
# POMOĆNE FUNKCIJE
# ============================================================================


def _racunaj_eta() -> str:
    """Računa preostalo vrijeme na osnovu prosječne brzine od starta."""
    pct = SHARED_STATS.get("pct", 0)
    if not _start_time or pct <= _start_pct or pct >= 100:
        return "--:--:--"
    elapsed = time.time() - _start_time
    done_pct = pct - _start_pct
    if done_pct <= 0:
        return "--:--:--"
    total_est = elapsed / (done_pct / 100.0)
    remaining = total_est - elapsed
    if remaining < 0:
        return "Uskoro..."
    h = int(remaining // 3600)
    m = int(remaining % 3600 // 60)
    s = int(remaining % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ============================================================================
# API RUTE
# ============================================================================


@bp.route("/api/files")
def get_files():
    """Skenira INPUT_DIR i vraća listu dostupnih EPUB fajlova."""
    try:
        path = Path(INPUT_DIR)
        if not path.exists():
            # Pokušaj automatske sanacije ako Termux storage nije mountan
            return jsonify(
                {"error": "Putanja nije dostupna", "path": str(path), "files": []}
            ), 404

        files = [f.name for f in path.glob("*.epub")]
        return jsonify({"files": sorted(files)})
    except Exception as e:
        print(f" Greška pri skeniranju fajlova: {e}")
        return jsonify({"files": [], "error": str(e)}), 500


@bp.route("/api/dev_models")
def dev_models():
    """Čita modele iz dev_api.json — vraća provajdere + V8_TURBO opciju."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        models = ["V10_TURBO", "V8_TURBO"] + [
            k for k in data.keys() if k.upper() not in skip
        ]
        return jsonify(models)
    except Exception:
        return jsonify(["V10_TURBO", "GEMINI", "GROQ", "CEREBRAS"])


@bp.route("/api/status")
def get_status():
    """Vraća kompletan status s ETA računanjem."""
    SHARED_STATS["est"] = _racunaj_eta()
    return jsonify(SHARED_STATS)


@bp.route("/api/start", methods=["POST"])
def start_processing():
    global _start_time, _start_pct
    try:
        data = request.get_json()
        if not data or "book" not in data:
            return jsonify({"error": "Nije odabran fajl"}), 400

        book = secure_filename(data["book"])
        model = data.get("model", "V10_TURBO")

        # Podržavamo tool (novi JS) i mode (stari JS)
        tool = data.get("tool", data.get("mode", "skriptorij")).upper()

        # Koristimo safe_path iz utils za validaciju putanje
        book_path = safe_path(book)

        # Finalna provjera postojanja fajla prije threada
        full_path = os.path.join(str(INPUT_DIR), book)
        if not os.path.exists(full_path):
            return jsonify(
                {"error": f"Fajl '{book}' ne postoji na lokaciji: {INPUT_DIR}"}
            ), 404

        SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})

        audit_entry = f"Sistem: Inicijalizacija modula '{tool}' za: {book}\n"
        SHARED_STATS.update(
            {
                "status": "POKRETANJE...",
                "current_file": book,
                "active_engine": model,
                "pct": 0,
                "ok": "0 / 0",
                "live_audit": SHARED_STATS.get("live_audit", "") + audit_entry,
                "output_file": "",
            }
        )

        _start_time = time.time()
        _start_pct = 0

        # Loguj zadnju knjigu za checkpoint
        try:
            with open(os.path.join(PROJECTS_ROOT, "last_book.json"), "w") as f:
                json.dump({"last_book": book}, f)
        except Exception:
            pass

        # Odabir modula: TTS ili Prevod
        if tool == "TTS":
            from tts import start_from_master as start_tts

            thread = threading.Thread(
                target=start_tts,
                args=(full_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )
        else:
            from skriptorij import start_skriptorij_from_master

            thread = threading.Thread(
                target=start_skriptorij_from_master,
                args=(full_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )

        thread.start()
        return jsonify({"status": "Started", "file": book, "tool": tool})

    except Exception as e:
        err_msg = traceback.format_exc()
        SHARED_STATS["status"] = "KRITIČNA GREŠKA"
        SHARED_STATS["live_audit"] += (
            f"<div class='p-2 text-red-500'>Greška pri startu: {str(e)}</div>"
        )
        print(f"\n[BACKEND ERROR]\n{err_msg}\n")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/reset", methods=["POST"])
def reset_route():
    SHARED_CONTROLS["reset"] = True
    # Reset statistike na nulu
    SHARED_STATS.update(
        {"pct": 0, "ok": "0 / 0", "status": "IDLE", "live_audit": "Sistem resetovan.\n"}
    )
    return jsonify({"status": "reset"})
