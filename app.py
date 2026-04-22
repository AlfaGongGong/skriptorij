"""
app.py — Flask aplikacijska fabrika za Skriptorij V8/V10 Turbo.
"""

from flask import Flask, make_response, redirect, render_template, request, jsonify
import traceback
from api_fleet import FleetManager, _active_fleet as _af_module

# NEMA zasebne _fleet instance ovdje.
# Koristimo istu instancu koju engine kreira i registrira putem
# register_active_fleet(). Fallback: kreiramo fresh za slučaj da engine
# još nije pokrenut (pri direktnom pregledavanju flote u IDLE modu).
_fleet_fallback = FleetManager(config_path="dev_api.json")

def _get_fleet():
    """Uvijek vrati aktivnu engine instancu ako postoji, inače fallback."""
    import api_fleet as _af
    return _af._active_fleet if _af._active_fleet is not None else _fleet_fallback


def create_app() -> Flask:
    """Kreira i konfigurira Flask aplikaciju."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # ── Intro ruta ────────────────────────────────────────────────────────────
    @app.route("/intro")
    def intro():
        return render_template("intro.html")

    # ── Index ruta ────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        from config.settings import SERVER_RUN_ID
        if request.cookies.get("intro_seen_run") != SERVER_RUN_ID:
            resp = make_response(redirect("/intro"))
            resp.set_cookie("intro_seen_run", SERVER_RUN_ID)
            return resp
        return render_template("index.html")

    # =========================================================================
    # FLEET RUTE — registrirane PRIJE Blueprinta da pobijede stari Blueprint kod
    # Flask koristi prvu registriranu rutu na istom URL-u
    # =========================================================================

    @app.route("/api/fleet")
    def api_fleet():
        """Vraća detaljan status flote za UI (V10 format)."""
        try:
            fleet = _get_fleet()
            return jsonify(fleet.get_fleet_ui())
        except Exception as e:
            print("❌ /api/fleet greška:", e)
            import traceback as _tb;
            print(_tb.format_exc())
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fleet/toggle", methods=["POST"])
    def api_fleet_toggle():
        """Toggle ključa u floti."""
        try:
            data = request.get_json(force=True) or {}
            provider = data.get("provider", "").upper()
            key      = data.get("key", "")
            if not provider or not key:
                return jsonify({"error": "Nedostaje provider ili key"}), 400
            return jsonify(_get_fleet().toggle_key(provider, key))
        except Exception as e:
            print("❌ /api/fleet/toggle greška:", e)
            import traceback as _tb; print(_tb.format_exc())
            return jsonify({"error": str(e)}), 500

    # ── Registracija Blueprint ruta (NAKON fleet ruta — ne mogu override-ovati) ─
    try:
        from api import register_blueprints
        from api.middleware import register_error_handlers
        register_blueprints(app)
        register_error_handlers(app)
    except ImportError as e:
        print(f"⚠️  Blueprint import greška: {e} — nastavljam bez Blueprint-a")

    return app


# Globalna instanca za direktno pokretanje
app = create_app()
