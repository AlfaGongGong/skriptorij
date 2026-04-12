"""Rute za kontrolu obrade (pause, resume, stop, reset)."""
from flask import Blueprint, jsonify

from config.settings import SHARED_STATS, SHARED_CONTROLS

bp = Blueprint("control", __name__)


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
        from api.routes.processing import reset_stats

        SHARED_CONTROLS["reset"] = True
        reset_stats()
    else:
        return jsonify({"error": f"Nepoznata akcija: {action}"}), 400
    return jsonify({"status": "ok", "action": action})
