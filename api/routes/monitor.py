"""api/routes/monitor.py — Real-time praćenje stanja ključeva."""
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
import time
from pathlib import Path

bp = Blueprint("monitor", __name__)


def _fleet():
    from api_fleet import get_active_fleet
    return get_active_fleet()


@bp.route("/api/monitor/status", methods=["GET"])
def status():
    fleet = _fleet()
    now = time.time()
    utc = datetime.now(timezone.utc)
    ponoc = utc.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400

    # QuotaTracker
    try:
        from network.quota_tracker import quota_tracker as qt
    except Exception:
        qt = None

    # Provider profili (RPM/RPD)
    try:
        from config.ai_config import PROVIDER_PROFILES as PP
    except Exception:
        PP = {}

    out = {
        "utc": utc.strftime("%H:%M:%S"),
        "ts": now,
        "reset_in_s": ponoc - now,
        "providers": {},
    }

    for prov, keys in fleet.fleet.items():
        if not keys:
            continue
        pu = prov.upper()
        pd = {"model": fleet.get_active_model(pu), "keys": []}
        prof = PP.get(pu)
        if prof:
            pd["rpm"] = getattr(prof, "rpm_limit", None)
            pd["rpd"] = getattr(prof, "rpd_limit", None)
        for ks in keys:
            k = ks.key if hasattr(ks, "key") else str(ks)
            short = k[:6] + "…" + k[-4:] if len(k) > 12 else k[:10]
            kd = {
                "key": short,
                "available": getattr(ks, "available", None),
                "success_rate": round(getattr(ks, "success_rate", 0.0), 3),
                "calls_ok": getattr(ks, "calls_ok", 0),
                "calls_failed": getattr(ks, "calls_failed", 0),
                "total_requests": getattr(ks, "total_requests", 0),
                "last_used_ago": round(now - getattr(ks, "last_used", 0.0), 1)
                    if getattr(ks, "last_used", 0.0) else None,
                "cooldown_left": round(max(0, getattr(ks, "cooldown_until", 0.0) - now), 1),
                "cooldown_reason": getattr(ks, "cooldown_reason", None),
            }
            if qt:
                try:
                    ok, reason = qt.is_key_available(pu, k)
                    kd["qt_available"] = ok
                    kd["qt_reason"] = None if ok else reason
                except Exception:
                    pass
            pd["keys"].append(kd)
        pd["n_total"] = len(pd["keys"])
        pd["n_available"] = sum(1 for x in pd["keys"] if x.get("available"))
        out["providers"][prov] = pd

    return jsonify(out)


@bp.route("/api/monitor/reset_key", methods=["POST"])
def reset_key():
    data = request.get_json(silent=True) or {}
    prov = (data.get("provider") or "").upper()
    prefix = data.get("key_prefix") or ""
    if not prov or not prefix:
        return jsonify({"ok": False, "error": "provider i key_prefix"}), 400
    fleet = _fleet()
    hit = 0
    try:
        from network.quota_tracker import quota_tracker as qt
    except Exception:
        qt = None
    for ks in fleet.fleet.get(prov, []):
        k = ks.key if hasattr(ks, "key") else str(ks)
        if k.startswith(prefix):
            if hasattr(ks, "cooldown_until"):
                ks.cooldown_until = 0.0
            if hasattr(ks, "cooldown_reason"):
                ks.cooldown_reason = None
            if qt:
                try: qt.reset(prov, k)
                except Exception: pass
            hit += 1
    return jsonify({"ok": True, "reset": hit})
