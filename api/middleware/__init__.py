

"""Middleware paket — error handlers."""
import logging
import sys

from flask import Flask

logger = logging.getLogger(__name__)

# ANSI boje za terminal
_RED    = "\x1b[1;91m"
_BRED   = "\x1b[1;97;41m"
_YELLOW = "\x1b[1;93m"
_RESET  = "\x1b[0m"


def _print_critical(prefix: str, msg: str, color: str = _RED) -> None:
    """Ispiši kritičnu grešku direktno u terminal."""
    try:
        sys.stdout.write(f"{color}[{prefix}] {msg}{_RESET}\n")
        sys.stdout.flush()
    except Exception:
        pass


def register_error_handlers(app: Flask) -> None:
    """Registrira globalne error handlere."""
    from flask import jsonify, request

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resurs nije pronađen"}), 404

    @app.errorhandler(500)
    def server_error(e):
        _print_critical(
            "GREŠKA 500",
            f"{request.method} {request.path} — {e}",
            color=_BRED,
        )
        logger.exception("Neočekivana interna greška: %s", e)
        return jsonify({"error": "Interna serverska greška"}), 500

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Neispravan zahtjev"}), 400

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        """Hvataj sve neočekivane iznimke i ispiši u terminal."""
        _print_critical(
            "KRITIČNA GREŠKA",
            f"Neuhvaćena iznimka na {request.method} {request.path}: {type(e).__name__}: {e}",
            color=_BRED,
        )
        logger.exception("Neuhvaćena iznimka: %s", e)
        return jsonify({"error": "Interna serverska greška"}), 500



