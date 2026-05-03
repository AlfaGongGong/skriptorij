

"""Rute za export izvještaja o prijevodu."""
import os

from flask import Blueprint, jsonify, Response

from config.settings import PROJECTS_ROOT, SHARED_STATS
from utils.file_utils import secure_filename

bp = Blueprint("export_routes", __name__)


@bp.route("/api/export/<fmt>")
def export_result(fmt):
    """Generiše i skida izvještaj o prijevodu u JSON ili TXT formatu."""
    output_file = SHARED_STATS.get("output_file", "")
    if not output_file:
        return jsonify({"error": "Nema završenog prijevoda"}), 404
    epub_path = os.path.join(PROJECTS_ROOT, secure_filename(output_file))
    if not os.path.exists(epub_path):
        return jsonify({"error": "EPUB fajl nije pronađen"}), 404
    try:
        from export_manager import generate_json_report, generate_txt_report

        if fmt == "json":
            data = generate_json_report(epub_path, SHARED_STATS)
            return Response(
                data,
                mimetype="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=izvjestaj_{output_file}.json"
                },
            )
        elif fmt == "txt":
            data = generate_txt_report(epub_path, SHARED_STATS)
            return Response(
                data,
                mimetype="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=izvjestaj_{output_file}.txt"
                },
            )
        else:
            return jsonify({"error": f"Nepoznat format: {fmt}"}), 400
    except Exception:
        return jsonify({"error": "Greška pri generiranju izvještaja"}), 500



