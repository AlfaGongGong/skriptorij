"""Middleware paket — error handlers."""
from flask import Flask


def register_error_handlers(app: Flask) -> None:
    """Registrira globalne error handlere."""
    from flask import jsonify

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resurs nije pronađen"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Interna serverska greška"}), 500

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Neispravan zahtjev"}), 400
