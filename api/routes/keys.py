

"""Rute za upravljanje API ključevima (CRUD)."""
import json
import re
import time

import requests
from flask import Blueprint, jsonify, request

from config.settings import CONFIG_PATH
from network.provider_urls import get_url as _get_provider_url

# Konstante za ping timeout
_PING_CONNECT_TIMEOUT = 8
_PING_READ_TIMEOUT    = 20

bp = Blueprint("keys", __name__)


def _reload_active_fleet() -> None:
    """Osvježava aktivni fleet iz diska ako postoji (tiho ignorira greške)."""
    try:
        from api_fleet import get_active_fleet
        fm = get_active_fleet()
        if fm is not None:
            fm.reload()
    except Exception:
        pass


@bp.route("/api/keys", methods=["GET"])
def list_keys():
    """Vraća listu provajdera i maskiran prikaz ključeva."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        result = {}
        for prov, val in data.items():
            if prov.upper() in skip:
                continue
            keys = val if isinstance(val, list) else val.get("keys", [])
            result[prov] = [
                f"...{k[-6:]}" if len(k) > 6 else "***" for k in keys if k
            ]
        return jsonify(result)
    except FileNotFoundError:
        return jsonify({})
    except Exception:
        return jsonify({"error": "Greška pri čitanju konfiguracije"}), 500


@bp.route("/api/keys/<provider>", methods=["POST"])
def add_key(provider):
    """Dodaje novi API ključ za provajdera i odmah aktivira provajdera u floti."""
    data = request.get_json()
    if not data or "key" not in data:
        return jsonify({"error": 'Nedostaje "key" polje'}), 400
    new_key = data["key"].strip()
    if not new_key:
        return jsonify({"error": "Prazan ključ"}), 400
    prov_upper = re.sub(r"[^A-Z0-9_]", "", provider.upper())
    if not prov_upper:
        return jsonify({"error": "Neispravan naziv provajdera"}), 400
    try:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except FileNotFoundError:
            cfg = {}
        if prov_upper not in cfg:
            cfg[prov_upper] = []
        existing = (
            cfg[prov_upper]
            if isinstance(cfg[prov_upper], list)
            else cfg[prov_upper].get("keys", [])
        )
        if new_key in existing:
            return jsonify({"error": "Ključ već postoji"}), 409
        if isinstance(cfg[prov_upper], list):
            cfg[prov_upper].append(new_key)
        else:
            cfg[prov_upper].setdefault("keys", []).append(new_key)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        # Odmah aktiviraj novi ključ u aktivnoj floti (bez restarta)
        _reload_active_fleet()
        return jsonify(
            {"status": "ok", "provider": prov_upper, "masked": f"...{new_key[-6:]}"}
        )
    except Exception:
        return jsonify({"error": "Greška pri dodavanju ključa"}), 500


@bp.route("/api/keys/<provider>/<int:idx>", methods=["DELETE"])
def delete_key(provider, idx):
    """Briše API ključ po indeksu za dati provajder i osvježava flotu."""
    prov_upper = re.sub(r"[^A-Z0-9_]", "", provider.upper())
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if prov_upper not in cfg:
            return jsonify({"error": "Provajder ne postoji"}), 404
        keys_list = (
            cfg[prov_upper]
            if isinstance(cfg[prov_upper], list)
            else cfg[prov_upper].get("keys", [])
        )
        if idx < 0 or idx >= len(keys_list):
            return jsonify({"error": "Indeks van opsega"}), 400
        keys_list.pop(idx)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        # Odmah ukloni obrisani ključ iz aktivne flote (bez restarta)
        _reload_active_fleet()
        return jsonify({"status": "ok", "provider": prov_upper})
    except Exception:
        return jsonify({"error": "Greška pri brisanju ključa"}), 500


@bp.route("/api/keys/<provider>/<int:idx>/ping", methods=["POST"])
def ping_key(provider, idx):
    """
    Testira API ključ minimalnim stvarnim pozivom provajderu.
    Vraća: { ok, latency_ms, status_code, error }
    """
    prov_upper = re.sub(r"[^A-Z0-9_]", "", provider.upper())
    if not prov_upper:
        return jsonify({"error": "Neispravan naziv provajdera"}), 400
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return jsonify({"error": "Konfiguracija ne postoji"}), 404
    except Exception:
        return jsonify({"error": "Greška pri čitanju konfiguracije"}), 500

    raw = cfg.get(prov_upper)
    if raw is None:
        return jsonify({"error": "Provajder ne postoji"}), 404
    keys_list = raw if isinstance(raw, list) else raw.get("keys", [])
    if idx < 0 or idx >= len(keys_list):
        return jsonify({"error": "Indeks van opsega"}), 400
    key = keys_list[idx].strip()
    if not key:
        return jsonify({"error": "Prazan ključ"}), 400

    from network.http_client import GOOGLE_MODEL_POOL
    from network.provider_router import MODEL_MAP
    url   = _get_provider_url(prov_upper)
    model = MODEL_MAP.get(prov_upper, "")
    if not model and prov_upper == "GEMINI":
        model = GOOGLE_MODEL_POOL[0]["model"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    payload = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ok"}],
    }

    t0 = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=(_PING_CONNECT_TIMEOUT, _PING_READ_TIMEOUT))
        latency = int((time.time() - t0) * 1000)
        sc = resp.status_code
        if sc == 200:
            return jsonify({"ok": True, "latency_ms": latency, "status_code": sc})
        elif sc == 429:
            try:
                body = resp.json()
                err = body.get("error", {}).get("message", str(body))[:120] if isinstance(body, dict) else str(body)[:120]
            except Exception:
                err = "Rate limit"
            return jsonify({"ok": False, "latency_ms": latency, "status_code": sc,
                            "error": f"429 Rate limit — {err}"})
        elif sc in (401, 403):
            return jsonify({"ok": False, "latency_ms": latency, "status_code": sc,
                            "error": "Ključ nevažeći (401/403)"})
        else:
            try:
                err = str(resp.json())[:120]
            except Exception:
                err = resp.text[:120]
            return jsonify({"ok": False, "latency_ms": latency, "status_code": sc, "error": err})
    except requests.exceptions.Timeout:
        latency = int((time.time() - t0) * 1000)
        return jsonify({"ok": False, "latency_ms": latency, "status_code": 0,
                        "error": "Timeout (20s)"})
    except Exception:
        latency = int((time.time() - t0) * 1000)
        return jsonify({"ok": False, "latency_ms": latency, "status_code": 0,
                        "error": "Mrežna greška pri ping testu"})
