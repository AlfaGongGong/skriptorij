"""Middleware paket — error handlers."""
import logging

from flask import Flask

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Registrira globalne error handlere."""
    from flask import jsonify

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resurs nije pronađen"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Neočekivana interna greška: %s", e)
        return jsonify({"error": "Interna serverska greška"}), 500

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Neispravan zahtjev"}), 400
