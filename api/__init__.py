"""API paket — registrira sve Blueprint rute."""
from flask import Flask
from .routes import books, processing, fleet, keys, export_routes, control


def register_blueprints(app: Flask) -> None:
    """Registrira sve Blueprint-e na Flask instancu."""
    app.register_blueprint(books.bp)
    app.register_blueprint(processing.bp)
    app.register_blueprint(fleet.bp)
    app.register_blueprint(keys.bp)
    app.register_blueprint(export_routes.bp)
    app.register_blueprint(control.bp)
