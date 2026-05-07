"""Rute za upravljanje knjigama (listanje, pretraga, upload)."""
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import INPUT_DIR
from utils.file_utils import secure_filename

bp = Blueprint("books", __name__)

_SUPPORTED_EXTS = {".epub", ".mobi"}


def _list_books() -> list[dict]:
    """Vraća listu dostupnih knjiga iz INPUT_DIR."""
    base = Path(INPUT_DIR)
    books = []
    for p in sorted(base.glob("*")):
        if p.suffix.lower() in _SUPPORTED_EXTS and not p.name.startswith("(LIVE)"):
            books.append({
                "name": p.name,
                "path": str(p),
                "size_bytes": p.stat().st_size,
            })
    return books


@bp.route("/api/books")
@bp.route("/api/files")
def api_books():
    """Vraća listu dostupnih EPUB/MOBI knjiga."""
    try:
        books = _list_books()
        return jsonify({"books": books, "files": [b["name"] for b in books]})
    except Exception:
        return jsonify({"error": "Greška pri čitanju knjiga", "books": [], "files": []}), 500


@bp.route("/api/upload_book", methods=["POST"])
def api_upload_book():
    """Prima i sprema uploadovanu knjigu u INPUT_DIR."""
    try:
        f = request.files.get("file")
        if not f or f.filename is None or f.filename == "":
            return jsonify({"error": "Nema fajla u zahtjevu"}), 400
        ext = Path(f.filename).suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            return jsonify({"error": f"Nepodržani format: {ext}"}), 400
        safe_name = secure_filename(f.filename)
        # Provjera path traversala — dest mora ostati unutar INPUT_DIR
        input_dir_real = os.path.realpath(INPUT_DIR)
        dest = os.path.realpath(os.path.join(input_dir_real, safe_name))
        if os.path.commonpath([input_dir_real, dest]) != input_dir_real:
            return jsonify({"error": "Neispravno ime fajla"}), 400
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        return jsonify({"ok": True, "name": safe_name})
    except Exception:
        return jsonify({"error": "Greška pri uploadu fajla"}), 500
