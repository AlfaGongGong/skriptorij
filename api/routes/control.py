"""Rute za kontrolu obrade (pause, resume, stop, reset)."""
import re
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import SHARED_STATS, SHARED_CONTROLS, CHECKPOINT_BASE_DIR

bp = Blueprint("control", __name__)


def _obrisi_checkpoint_i_kes(book: str, log=False) -> dict:
    """
    Briše cijeli _skr_<stem> direktorij (checkpointi + keš) iz CHECKPOINT_BASE_DIR
    za datu knjigu.

    Vraća rječnik s rezultatom: {"ok": bool, "obrisano_dir": str|None, "greska": str|None}
    """
    from utils.checkpoint_cleaner import full_reset
    stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(book).stem)
    result = full_reset(stem)
    if log:
        print(f"[control/reset] full_reset('{stem}') → {result}")
    return result


@bp.route("/control/<action>", methods=["POST"])
def control_process(action):
    if action == "pause":
        SHARED_CONTROLS["pause"] = True
        SHARED_STATS["status"] = "PAUZIRANO"

    elif action == "resume":
        SHARED_CONTROLS["pause"] = False
        SHARED_STATS["status"] = "OBRADA U TOKU..."

    elif action == "stop":
        SHARED_CONTROLS["stop"] = True
        SHARED_STATS["status"] = "ZAUSTAVLJENO"

    elif action == "reset":
        SHARED_CONTROLS["stop"]  = True
        SHARED_CONTROLS["pause"] = False
        SHARED_CONTROLS["reset"] = True

        # Briši checkpointe i keš za aktivnu knjigu
        active_book = SHARED_STATS.get("current_file", "")
        reset_result = {}
        if active_book:
            reset_result = _obrisi_checkpoint_i_kes(active_book, log=True)

        # Resetuj SHARED_STATS
        SHARED_STATS.update({
            "status": "IDLE",
            "pct": 0,
            "ok": "0 / 0",
            "skipped": 0,
            "current_file": "",
            "active_engine": "---",
            "live_audit": "Sistem resetovan.\n",
            "output_file": "",
            "quality_scores": {},
            "glosar_problemi": {},
            "knjiga_mode": None,
            "knjiga_mode_info": "",
        })
        return jsonify({
            "status": "ok",
            "action": action,
            "reset": reset_result,
        })

    else:
        return jsonify({"error": f"Nepoznata akcija: {action}"}), 400

    return jsonify({"status": "ok", "action": action})