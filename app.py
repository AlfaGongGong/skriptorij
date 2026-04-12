"""
app.py — Flask aplikacijska fabrika za Skriptorij V8 Turbo.

Kreira i konfigurira Flask instancu s registrovanim Blueprint rutama.
Uvozi i koristi dijeljeno stanje iz config.settings.
"""

import os

from flask import Flask, make_response, redirect, render_template, request


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

    # ── Intro ruta ────────────────────────────────────────────────────────────
    @app.route("/intro")
    def intro():
        return render_template("intro.html")

    # ── Index ruta ────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        # On first visit redirect to /intro; cookie persists for 30 days
        if not request.cookies.get("intro_seen"):
            resp = make_response(redirect("/intro"))
            resp.set_cookie("intro_seen", "true", max_age=3600 * 24 * 30)
            return resp
        return render_template("index.html")

    return app


# Globalna instanca za direktno pokretanje i importovanje u main.py
app = create_app()
