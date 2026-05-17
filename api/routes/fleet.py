

"""Rute za Fleet Pool — prikaz API ključeva i statistike poziva."""
import logging

from flask import Blueprint, jsonify

from config.settings import CONFIG_PATH

logger = logging.getLogger(__name__)



def _normalize_fleet_summary(raw: dict) -> dict:
    """
    Normalizuje get_fleet_ui() output u format koji renderFleet() razumije:
      { "PROVIDER": { "total": int, "keys": [...] }, ... }
    """
    if not raw or not isinstance(raw, dict):
        return {}

    # Format A: wrapped u "providers" ključ
    if "providers" in raw and isinstance(raw["providers"], dict):
        raw = raw["providers"]

    result = {}
    for prov, info in raw.items():
        if prov in ("total_active", "total_keys", "summary", "error"):
            continue
        if not isinstance(info, dict):
            continue

        keys = info.get("keys", [])
        if not isinstance(keys, list):
            keys = []

        norm_keys = []
        for k in keys:
            if isinstance(k, str):
                norm_keys.append({
                    "masked":          "..." + k[-6:] if len(k) > 6 else "***",
                    "available":       True,
                    "calls_ok":        0,
                    "calls_failed":    0,
                    "calls_rejected":  {},
                    "success_rate":    1.0,
                    "total_requests":  0,
                    "rpm":             0,
                    "rpm_safe":        0,
                    "rpd":             0,
                    "rpd_safe":        0,
                    "tpd":             0,
                    "cooldown_s":      0.0,
                    "cooldown_reason": "",
                })
            elif isinstance(k, dict):
                norm_keys.append({
                    "masked":          k.get("masked", k.get("key", "???")),
                    "available":       k.get("available", True),
                    "calls_ok":        k.get("calls_ok", 0),
                    "calls_failed":    k.get("calls_failed", 0),
                    "calls_rejected":  k.get("calls_rejected", {}),
                    "success_rate":    k.get("success_rate", 1.0),
                    "total_requests":  k.get("total_requests", 0),
                    "rpm":             k.get("rpm", 0),
                    "rpm_safe":        k.get("rpm_safe", 0),
                    "rpd":             k.get("rpd", 0),
                    "rpd_safe":        k.get("rpd_safe", 0),
                    "tpd":             k.get("tpd", 0),
                    "cooldown_s":      k.get("cooldown_s", 0.0),
                    "cooldown_reason": k.get("cooldown_reason", ""),
                })

        total = info.get("total", len(norm_keys))

        avg_sr = (
            round(sum(k.get("success_rate", 1.0) for k in norm_keys) / len(norm_keys), 4)
            if norm_keys else 1.0
        )
        result[prov.upper()] = {
            "total":        int(total),
            "active":       int(total),
            "success_rate": avg_sr,
            "keys":         norm_keys,
        }

    return result

bp = Blueprint("fleet", __name__)


@bp.route("/api/fleet")
def get_fleet():
    """Vraća detalje flote za Fleet Pool prikaz (s per-key statistikama poziva)."""
    try:
        from api_fleet import FleetManager, get_active_fleet

        fm = get_active_fleet()
        if fm is None:
            fm = FleetManager(config_path=CONFIG_PATH)
        data = _normalize_fleet_summary(fm.get_fleet_ui())
        logger.debug("[fleet] GET /api/fleet — %d provajdera", len(data))
        return jsonify(data)
    except Exception:
        logger.exception("[fleet] Greška pri dohvaćanju flote")
        return jsonify({"error": "Greška pri dohvaćanju flote"}), 500


