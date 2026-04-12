"""
app.py — Flask aplikacijska fabrika za Skriptorij V8 Turbo.

Kreira i konfigurira Flask instancu s registrovanim Blueprint rutama.
Uvozi i koristi dijeljeno stanje iz config.settings.
"""

import os

from flask import Flask, render_template


def create_app() -> Flask:
    """Kreira i konfigurira Flask aplikaciju."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # ── Registracija Blueprint ruta ───────────────────────────────────────────
    from api import register_blueprints
    from api.middleware import register_error_handlers

    register_blueprints(app)
    register_error_handlers(app)

    # ── Index ruta ────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        try:
            from intro_ui import INTRO_HTML
        except ImportError:
            INTRO_HTML = ""
        return render_template("index.html", introhtml=INTRO_HTML)

    return app


# Globalna instanca za direktno pokretanje i importovanje u main.py
app = create_app()
