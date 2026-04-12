"""Rute za Fleet Pool — prikaz i upravljanje API ključevima."""
from flask import Blueprint, jsonify, request

from config.settings import CONFIG_PATH

bp = Blueprint("fleet", __name__)


@bp.route("/api/fleet")
def get_fleet():
    """Vraća detalje flote za Fleet Pool prikaz."""
    try:
        from api_fleet import FleetManager, get_active_fleet

        fm = get_active_fleet()
        if fm is None:
            fm = FleetManager(config_path=CONFIG_PATH)
        return jsonify(fm.get_fleet_summary())
    except Exception:
        return jsonify({"error": "Greška pri dohvaćanju flote"}), 500


@bp.route("/api/fleet/toggle", methods=["POST"])
def toggle_fleet_key():
    """Uključuje/isključuje pojedinačni API ključ u floti."""
    try:
        from api_fleet import FleetManager, get_active_fleet

        data = request.get_json()
        if not data or "provider" not in data or "key" not in data:
            return jsonify({"error": "Nedostaju polja provider i/ili key"}), 400
        fm = get_active_fleet()
        if fm is None:
            fm = FleetManager(config_path=CONFIG_PATH)
        new_state = fm.toggle_key(data["provider"], data["key"])
        if new_state is None:
            return jsonify({"error": "Ključ nije pronađen"}), 404
        return jsonify(
            {"provider": data["provider"], "key": data["key"], "disabled": new_state}
        )
    except Exception:
        return jsonify({"error": "Interna greška pri toggleu ključa"}), 500
