"""Rute za upravljanje knjigama (upload, listing)."""
import json
import os

from flask import Blueprint, jsonify, request

from config.settings import PROJECTS_ROOT
from utils.file_utils import secure_filename, safe_path

bp = Blueprint("books", __name__)


@bp.route("/api/books")
def list_books():
    os.makedirs(PROJECTS_ROOT, exist_ok=True)
    files = sorted(
        f for f in os.listdir(PROJECTS_ROOT) if f.lower().endswith((".epub", ".mobi"))
    )
    try:
        with open(os.path.join(PROJECTS_ROOT, "last_book.json"), "r") as f:
            last = json.load(f).get("last_book")
    except Exception:
        last = None
    return jsonify({"books": [{"name": f, "path": f} for f in files], "last_book": last})


@bp.route("/api/upload_book", methods=["POST"])
def upload_book():
    if "file" not in request.files:
        return jsonify({"error": "Nema fajla"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Prazno ime fajla"}), 400
    filename = secure_filename(f.filename)
    path = safe_path(filename)
    f.save(path)
    return jsonify({"status": "ok", "name": filename})


@bp.route("/api/download/<path:filename>")
def download_file(filename):
    from flask import send_from_directory

    safe = secure_filename(filename)
    full = os.path.realpath(os.path.join(PROJECTS_ROOT, safe))
    if not full.startswith(os.path.realpath(PROJECTS_ROOT)):
        return jsonify({"error": "Neispravan zahtjev"}), 400
    if not os.path.exists(full):
        return jsonify({"error": "Fajl nije pronađen"}), 404
    return send_from_directory(PROJECTS_ROOT, safe, as_attachment=True)
