"""Rute za upravljanje obradom knjiga (start, status, modeli)."""
import json
import os
import threading
import time

from flask import Blueprint, jsonify, request

from config.settings import PROJECTS_ROOT, SHARED_STATS, SHARED_CONTROLS, CONFIG_PATH
from utils.file_utils import secure_filename, safe_path

bp = Blueprint("processing", __name__)

# Globalno praćenje vremena za ETA računanje
_start_time: float | None = None
_start_pct: float = 0


def reset_stats():
    global _start_time, _start_pct
    _start_time = None
    _start_pct = 0
    SHARED_STATS.update(
        {
            "status": "RESETOVANO",
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
            "live_audit": "Sesija resetovana.\n",
            "output_file": "",
            "stvarno_prevedeno": 0,
            "spaseno_iz_checkpointa": 0,
        }
    )
    SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})


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


@bp.route("/api/dev_models")
def dev_models():
    """Čita modele iz dev_api.json — vraća provajdere + V8_TURBO opciju."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        models = ["V8_TURBO"] + [k for k in data.keys() if k.upper() not in skip]
        return jsonify(models)
    except Exception:
        return jsonify(["V8_TURBO", "GEMINI", "GROQ", "CEREBRAS"])


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
        model = data.get("model", "V8_TURBO")
        mode = data.get("mode", "PREVOD").upper()
        book_path = safe_path(book)
        if not os.path.exists(book_path):
            return jsonify({"error": f"Fajl '{book}' ne postoji na serveru"}), 404
        SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})
        SHARED_STATS.update(
            {
                "status": "POKRETANJE...",
                "current_file": book,
                "active_engine": model,
                "pct": 0,
                "ok": "0 / 0",
                "live_audit": f"Inicijalizacija za: {book}\n",
                "output_file": "",
            }
        )
        _start_time = time.time()
        _start_pct = 0
        try:
            with open(os.path.join(PROJECTS_ROOT, "last_book.json"), "w") as f:
                json.dump({"last_book": book}, f)
        except Exception:
            pass
        if mode == "TTS":
            from tts import start_from_master as start_tts
            thread = threading.Thread(
                target=start_tts,
                args=(book_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )
        else:
            from skriptorij import start_skriptorij_from_master
            thread = threading.Thread(
                target=start_skriptorij_from_master,
                args=(book_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )
        thread.start()
        return jsonify({"status": "Started", "file": book, "mode": mode})
    except ValueError:
        return jsonify({"error": "Neispravan naziv fajla ili putanja"}), 400
    except Exception:
        SHARED_STATS["status"] = "GREŠKA PRI STARTU"
        return jsonify({"error": "Greška pri pokretanju obrade"}), 500
