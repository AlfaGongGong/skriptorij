"""API paket — registrira sve Blueprint rute.

NAPOMENA: Ovaj paket trenutno NIJE aktiviran u app.py create_app().
Sve rute su direktno definirane u app.py (monolitni pristup).
Blueprintovi su pripremljeni za buduću modularizaciju.
Da aktivirate blueprintove, dodajte u create_app():
    from api import register_blueprints
    register_blueprints(app)
Ali pažnja — to će kreirati duplikat ruta s app.py rutama!
"""
from flask import Flask
from .routes import books, processing, fleet, keys, export_routes, control
from api.routes.qualities import bp as quality_bp


def register_blueprints(app: Flask) -> None:
    """Registrira sve Blueprint-e na Flask instancu."""
    app.register_blueprint(quality_bp)
    app.register_blueprint(books.bp)
    app.register_blueprint(processing.bp)
    app.register_blueprint(fleet.bp)
    app.register_blueprint(keys.bp)
    app.register_blueprint(export_routes.bp)
    app.register_blueprint(control.bp)



