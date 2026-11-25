"""File Browser endpointi za BOOKLYFI"""

import os
import shutil
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import INPUT_DIR

bp = Blueprint("file_browser", __name__)


def _dozvoljeni_korijeni():
    """L57: browse/upload samo unutar /storage, /sdcard, INPUT_DIR i OUTPUT_DIR
    (ili BOOKLYFI_BROWSE_ROOTS, odvojeno s ':')."""
    ev = os.environ.get("BOOKLYFI_BROWSE_ROOTS", "").strip()
    if ev:
        return [os.path.normpath(x) for x in ev.split(os.pathsep) if x.strip()]
    korijeni = ["/storage", "/sdcard", str(INPUT_DIR)]
    try:
        from config.settings import OUTPUT_DIR

        korijeni.append(str(OUTPUT_DIR))
    except Exception:
        pass
    return [os.path.normpath(x) for x in korijeni]


def _dozvoljena(putanja) -> bool:
    p = os.path.normpath(os.path.abspath(str(putanja)))  # normpath uklanja '..'
    return any(p == r or p.startswith(r.rstrip(os.sep) + os.sep) for r in _dozvoljeni_korijeni())


@bp.route("/api/upload_from_path", methods=["POST"])
def api_upload_from_path():
    try:
        data = request.get_json(force=True)
        source_path = data.get("path", "").strip()
        if not source_path:
            return jsonify({"error": "Nedostaje putanja"}), 400
        if not _dozvoljena(source_path):
            return jsonify({"error": "Putanja izvan dozvoljenih mapa"}), 403
        source = Path(source_path)
        if not source.exists():
            return jsonify({"error": f"Fajl ne postoji: {source_path}"}), 404
        if source.suffix.lower() not in {".epub", ".mobi", ".pdf"}:
            return jsonify({"error": "Samo EPUB, MOBI i PDF"}), 400
        dest = Path(INPUT_DIR) / source.name
        if source.resolve() != dest.resolve():
            shutil.copy2(str(source), str(dest))
        return jsonify({"ok": True, "name": source.name, "path": str(dest)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/browse_files", methods=["POST"])
def api_browse_files():
    try:
        data = request.get_json(force=True)
        browse_path = data.get("path", "/storage/emulated/0").strip()
        if not _dozvoljena(browse_path):
            return jsonify({"error": "Putanja izvan dozvoljenih mapa", "files": []}), 403
        path = Path(browse_path)
        if not path.exists():
            path = Path("/storage/emulated/0")
        files = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith("."):
                    continue
                info = {
                    "name": item.name,
                    "path": str(item),
                    "type": "folder" if item.is_dir() else "file",
                }
                if item.is_file():
                    info["epub"] = item.suffix.lower() in {".epub", ".mobi", ".pdf"}
                files.append(info)
        except PermissionError:
            return jsonify({"error": "Nemate pristup", "files": []}), 403
        return jsonify(
            {
                "path": str(path),
                "parent": str(path.parent) if path.parent != path else None,
                "files": files,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
