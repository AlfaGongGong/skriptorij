"""Rute za upravljanje API ključevima (CRUD)."""
import json
import re

from flask import Blueprint, jsonify, request

from config.settings import CONFIG_PATH

bp = Blueprint("keys", __name__)


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
    """Dodaje novi API ključ za provajdera."""
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
        return jsonify(
            {"status": "ok", "provider": prov_upper, "masked": f"...{new_key[-6:]}"}
        )
    except Exception:
        return jsonify({"error": "Greška pri dodavanju ključa"}), 500


@bp.route("/api/keys/<provider>/<int:idx>", methods=["DELETE"])
def delete_key(provider, idx):
    """Briše API ključ po indeksu za dati provajder."""
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
        return jsonify({"status": "ok", "provider": prov_upper})
    except Exception:
        return jsonify({"error": "Greška pri brisanju ključa"}), 500
