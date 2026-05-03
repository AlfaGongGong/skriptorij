

"""Rute za Fleet Pool — prikaz i upravljanje API ključevima."""
from flask import Blueprint, jsonify, request

from config.settings import CONFIG_PATH



def _normalize_fleet_summary(raw: dict) -> dict:
    """
    Normalizuje get_fleet_summary() output u format koji renderFleet() razumije:
      { "PROVIDER": { "active": int, "total": int, "keys": [...] }, ... }

    Podržava više mogućih formata koje FleetManager može vraćati:
      - Već ispravan flat dict
      - { "providers": { ... } } wrapper
      - { "PROV": { "keys": [...], "enabled": N, ... } } varijanta
    """
    if not raw or not isinstance(raw, dict):
        return {}

    # Format A: wrapped u "providers" ključ
    if "providers" in raw and isinstance(raw["providers"], dict):
        raw = raw["providers"]

    result = {}
    for prov, info in raw.items():
        # Preskoči meta ključeve
        if prov in ("total_active", "total_keys", "summary", "error"):
            continue
        if not isinstance(info, dict):
            continue

        keys = info.get("keys", [])
        if not isinstance(keys, list):
            keys = []

        # Normalizuj svaki key objekt
        norm_keys = []
        for k in keys:
            if isinstance(k, str):
                # Format gdje je key samo string (API key vrijednost)
                norm_keys.append({
                    "key": k[:8] + "...",
                    "available": True,
                    "disabled": False,
                    "cooldown_remaining": 0,
                    "errors": 0,
                    "requests": 0,
                })
            elif isinstance(k, dict):
                norm_keys.append({
                    "key":                k.get("key", k.get("id", "???"))[:8] + "...",
                    "available":          k.get("available", k.get("active", not k.get("disabled", False))),
                    "disabled":           k.get("disabled", False),
                    "cooldown_remaining": k.get("cooldown_remaining", k.get("cooldown", 0)),
                    "errors":             k.get("errors", k.get("error_count", 0)),
                    "requests":           k.get("requests", k.get("total_requests", 0)),
                })

        # Izračunaj active/total
        active = info.get("active", info.get("enabled", None))
        total  = info.get("total",  info.get("count", None))

        if active is None:
            active = sum(1 for k in norm_keys if k["available"] and not k["disabled"])
        if total is None:
            total = len(norm_keys) if norm_keys else info.get("key_count", 0)

        result[prov.upper()] = {
            "active": int(active),
            "total":  int(total),
            "keys":   norm_keys,
        }

    return result

bp = Blueprint("fleet", __name__)


@bp.route("/api/fleet")
def get_fleet():
    """Vraća detalje flote za Fleet Pool prikaz."""
    try:
        from api_fleet import FleetManager, get_active_fleet

        fm = get_active_fleet()
        if fm is None:
            fm = FleetManager(config_path=CONFIG_PATH)
        return jsonify(_normalize_fleet_summary(fm.get_fleet_summary()))
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
        result = fm.toggle_key(data["provider"], data["key"])
        if result is None or "error" in result:
            return jsonify({"error": result.get("error", "Ključ nije pronađen") if result else "Ključ nije pronađen"}), 404
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Interna greška pri toggleu ključa"}), 500



