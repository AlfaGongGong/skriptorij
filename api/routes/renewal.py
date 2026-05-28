"""api/routes/renewal.py

REST endpointi za key renewal (dostupni i kao Blueprint i inline u app.py).
Koristi se iz app.py direktno — ovaj fajl je za modularni import.
"""
import json, logging, re
from flask import Blueprint, jsonify, request
from config.settings import CONFIG_PATH

logger = logging.getLogger(__name__)
bp = Blueprint("renewal", __name__)

_VALID_MODES = {"rpm_reset", "rpd_reset", "full_reset", "unban"}
_BATCH_MODES = {"rpd_reset", "full_reset", "unban"}
_RENEWAL_LABELS = {
    "rpm_reset":  "Minutni RPM cooldown resetovan",
    "rpd_reset":  "Dnevna kvota resetovana (provider ponoćni reset)",
    "full_reset": "Potpuni reset ključa (regenerisan ili operatorski)",
    "unban":      "Ključ odbanovan (provider reaktivirao nalog)",
}

def _get_key_from_config(prov_upper: str, idx: int):
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    raw = cfg.get(prov_upper)
    if raw is None:
        return None
    keys_list = raw if isinstance(raw, list) else raw.get("keys", [])
    if idx < 0 or idx >= len(keys_list):
        return None
    return keys_list[idx].strip() or None

@bp.route("/api/keys/<provider>/<int:idx>/renew", methods=["POST"])
def renew_key_endpoint(provider, idx):
    prov_upper = re.sub(r"[^A-Z0-9_]", "", provider.upper())
    if not prov_upper:
        return jsonify({"error": "Neispravan naziv provajdera"}), 400
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "").strip().lower()
    if mode not in _VALID_MODES:
        return jsonify({"error": f"Neispravan mode. Dozvoljeni: {sorted(_VALID_MODES)}", "valid_modes": sorted(_VALID_MODES)}), 400
    key = _get_key_from_config(prov_upper, idx)
    if key is None:
        return jsonify({"error": f"Ključ [{idx}] za {prov_upper} nije pronađen"}), 404
    try:
        from network.key_renewal import renew_key
        result = renew_key(prov_upper, key, mode)
        result["mode_label"] = _RENEWAL_LABELS.get(mode, mode)
        return jsonify(result), 200 if result["ok"] else 500
    except Exception:
        logger.exception("[renewal] Greška")
        return jsonify({"error": "Interna greška"}), 500

@bp.route("/api/keys/<provider>/renew_all", methods=["POST"])
def renew_all_keys_endpoint(provider):
    prov_upper = re.sub(r"[^A-Z0-9_]", "", provider.upper())
    if not prov_upper:
        return jsonify({"error": "Neispravan naziv provajdera"}), 400
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "").strip().lower()
    if mode not in _BATCH_MODES:
        return jsonify({"error": f"Neispravan mode. Za renew_all dozvoljeni: {sorted(_BATCH_MODES)}", "valid_modes": sorted(_BATCH_MODES)}), 400
    try:
        from network.key_renewal import renew_provider
        result = renew_provider(prov_upper, mode)
        result["mode_label"] = _RENEWAL_LABELS.get(mode, mode)
        status = 200 if result["ok"] else (207 if result.get("success", 0) > 0 else 500)
        return jsonify(result), status
    except Exception:
        logger.exception("[renewal] Greška renew_all")
        return jsonify({"error": "Interna greška"}), 500
