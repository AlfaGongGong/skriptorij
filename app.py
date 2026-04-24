"""
app.py — Flask aplikacijska fabrika za Booklyfi Turbo V10.2
ISPRAVLJENA VERZIJA:
  - Sve kritične /api/* rute definirane DIREKTNO ovdje (ne oslanjaju se na Blueprint)
  - Blueprint-i se i dalje pokušavaju učitati, ali greška ih ne ruši server
  - app.config ispravno postavljen PRIJE app.run()
  - Dodan /api/books, /api/files, /api/status, /api/start,
    /api/dev_models, /api/keys/*, /control/*, /api/upload_book
"""

import os
import json
import threading
import traceback
from pathlib import Path
from flask import (Flask, make_response, redirect, render_template,
                   request, jsonify, send_file)
from api_fleet import FleetManager

# ── Fleet singleton ───────────────────────────────────────────────────────────
_fleet_fallback = FleetManager(config_path="dev_api.json")

def _get_fleet() -> FleetManager:
    import api_fleet as _af
    return _af._active_fleet if _af._active_fleet is not None else _fleet_fallback


# ── Shared state (importovano ili lokalni fallback) ───────────────────────────
try:
    from config.settings import SHARED_STATS, SHARED_CONTROLS, INPUT_DIR, SERVER_RUN_ID
except ImportError:
    INPUT_DIR = Path("data")
    SERVER_RUN_ID = "dev"
    SHARED_STATS: dict = {
        "status": "IDLE", "pct": 0, "ok": "0 / 0", "skipped": 0,
        "current_file": "", "active_engine": "---",
        "fleet_active": 0, "fleet_cooling": 0,
        "live_audit": "", "output_file": None, "est": "--:--:--",
    }
    SHARED_CONTROLS: dict = {"stop": False, "pause": False}

_engine_thread: threading.Thread | None = None


# ── Helper: lista EPUB/MOBI fajlova ──────────────────────────────────────────
def _list_books() -> list[dict]:
    base = Path(INPUT_DIR) if not isinstance(INPUT_DIR, Path) else INPUT_DIR
    exts = {".epub", ".mobi"}
    books = []
    for p in sorted(base.glob("*")):
        if p.suffix.lower() in exts and not p.name.startswith("(LIVE)"):
            books.append({"name": p.name, "path": str(p), "size_bytes": p.stat().st_size})
    return books


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # FIX: mora biti PRIJE run()
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB upload limit

    # ═════════════════════════════════════════════════════════════════════════
    # STRANICE
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/intro")
    def intro():
        return render_template("intro.html")

    @app.route("/")
    def index():
        if request.cookies.get("intro_seen_run") != SERVER_RUN_ID:
            resp = make_response(redirect("/intro"))
            resp.set_cookie("intro_seen_run", SERVER_RUN_ID)
            return resp
        return render_template("index.html")

    # ═════════════════════════════════════════════════════════════════════════
    # KNJIGE — /api/books i /api/files (oba endpointa, isti odgovor)
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/books")
    @app.route("/api/files")
    def api_books():
        try:
            books = _list_books()
            # Vraćamo i books i files ključeve za kompatibilnost s oba frontend-a
            return jsonify({
                "books": books,
                "files": [b["name"] for b in books],
            })
        except Exception as e:
            print("api/books greska:", traceback.format_exc())
            return jsonify({"error": str(e), "books": [], "files": []}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # UPLOAD — /api/upload_book
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/upload_book", methods=["POST"])
    def api_upload_book():
        try:
            f = request.files.get("file")
            if not f:
                return jsonify({"error": "Nema fajla u zahtjevu"}), 400
            ext = Path(f.filename).suffix.lower()
            if ext not in {".epub", ".mobi"}:
                return jsonify({"error": f"Nepodržani format: {ext}"}), 400

            dest = Path(INPUT_DIR) / f.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.save(dest)
            return jsonify({"ok": True, "name": f.filename, "path": str(dest)})
        except Exception as e:
            print("api/upload_book greska:", traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # MODELI — /api/dev_models
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/dev_models")
    def api_dev_models():
        try:
            # Pokušaj učitati iz dev_api.json
            models = []
            try:
                raw = json.loads(Path("dev_api.json").read_text("utf-8"))
                has_keys = {
                    prov.upper() for prov, v in raw.items()
                    if prov.upper() not in {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
                    and (
                        (isinstance(v, list) and any(k.strip() for k in v if isinstance(k, str)))
                        or (isinstance(v, dict) and v)
                    )
                }
                if has_keys:
                    models.append("V10_TURBO")
                    models.append("V8_TURBO")
                    # Dodaj individualne provajdere s ključevima
                    for prov in ["GEMINI", "GROQ", "CEREBRAS", "MISTRAL", "SAMBANOVA",
                                  "TOGETHER", "OPENROUTER", "COHERE", "CHUTES",
                                  "HUGGINGFACE", "KLUSTER", "FIREWORKS", "GEMMA"]:
                        if prov in has_keys:
                            models.append(prov)
            except Exception:
                pass

            if not models:
                models = ["V10_TURBO", "V8_TURBO", "GEMINI", "GROQ", "MISTRAL"]

            return jsonify(models)
        except Exception as e:
            return jsonify(["V10_TURBO", "V8_TURBO"]), 200

    # ═════════════════════════════════════════════════════════════════════════
    # STATUS — /api/status
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/status")
    def api_status():
        try:
            fleet = _get_fleet()
            summary = fleet.get_fleet_summary()
            active_keys = sum(v["active"] for v in summary.values())
            cooling_keys = sum(v["cooling"] for v in summary.values())

            return jsonify({
                **SHARED_STATS,
                "fleet_active": active_keys,
                "fleet_cooling": cooling_keys,
            })
        except Exception as e:
            return jsonify({**SHARED_STATS, "error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # START — /api/start
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/start", methods=["POST"])
    def api_start():
        global _engine_thread

        try:
            data = request.get_json(force=True) or {}
            book  = data.get("book", "").strip()
            model = data.get("model", "V10_TURBO").strip()
            mode  = data.get("mode", "FUSION").strip()

            if not book:
                return jsonify({"error": "Nedostaje 'book' parametar"}), 400

            # Provjeri da fajl postoji
            book_path = Path(book) if Path(book).is_absolute() else Path(INPUT_DIR) / book
            if not book_path.exists():
                # Fallback: traži samo po imenu
                found = list(Path(INPUT_DIR).glob(f"**/{book_path.name}"))
                if not found:
                    return jsonify({"error": f"Knjiga nije pronađena: {book}"}), 404
                book_path = found[0]

            # Provjeri da nije već u toku
            if SHARED_STATS.get("status", "IDLE") not in ("IDLE", "ZAUSTAVLJENO", "GREŠKA"):
                if _engine_thread and _engine_thread.is_alive():
                    return jsonify({"error": "Obrada je već u toku. Zaustavi je prvo."}), 409

            # Reset stanja
            SHARED_CONTROLS["stop"] = False
            SHARED_CONTROLS["pause"] = False
            SHARED_STATS.update({
                "status": "POKRETANJE...",
                "pct": 0,
                "ok": "0 / 0",
                "skipped": 0,
                "current_file": "",
                "active_engine": model,
                "live_audit": "",
                "output_file": None,
                "est": "--:--:--",
            })

            def run_engine():
                try:
                    from run import start_skriptorij_from_master
                    start_skriptorij_from_master(
                        str(book_path), model, SHARED_STATS, SHARED_CONTROLS
                    )
                except ImportError:
                    import skriptorij
                    skriptorij.start_skriptorij_from_master(
                        str(book_path), model, SHARED_STATS, SHARED_CONTROLS
                    )
                except Exception as exc:
                    print("Engine greska:", traceback.format_exc())
                    SHARED_STATS["status"] = f"GREŠKA: {type(exc).__name__}"
                    SHARED_STATS["live_audit"] += f"\nGreska: {exc}"
            _engine_thread = threading.Thread(target=run_engine, daemon=True, name="booklyfi-engine")
            _engine_thread.start()

            return jsonify({"ok": True, "book": book_path.name, "model": model, "mode": mode})

        except Exception as e:
            print("api/start greska:", traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # KONTROLA — /control/<action>
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/control/<action>", methods=["POST"])
    def control(action):
        try:
            action = action.lower()
            if action == "pause":
                SHARED_CONTROLS["pause"] = True
                SHARED_STATS["status"] = "PAUZIRANO"
            elif action == "resume":
                SHARED_CONTROLS["pause"] = False
                SHARED_STATS["status"] = "OBRADA U TOKU..."
            elif action == "stop":
                SHARED_CONTROLS["stop"] = True
                SHARED_CONTROLS["pause"] = False
                SHARED_STATS["status"] = "ZAUSTAVLJENO"
            elif action == "reset":
                SHARED_CONTROLS["stop"] = True
                SHARED_CONTROLS["pause"] = False
                SHARED_STATS.update({
                    "status": "IDLE", "pct": 0, "ok": "0 / 0",
                    "skipped": 0, "current_file": "", "active_engine": "---",
                    "live_audit": "", "output_file": None,
                })
            else:
                return jsonify({"error": f"Nepoznata akcija: {action}"}), 400

            return jsonify({"ok": True, "action": action})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # API KLJUČEVI — /api/keys
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/keys")
    def api_keys_get():
        """Vraća maskirane API ključeve po provajderu."""
        try:
            fleet = _get_fleet()
            result = {}
            for prov, keys in fleet.fleet.items():
                if keys:
                    result[prov] = [ks.masked for ks in keys]
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/keys/<provider>", methods=["POST"])
    def api_keys_add(provider):
        """Dodaje novi API ključ za provajdera u dev_api.json."""
        try:
            data = request.get_json(force=True) or {}
            key = data.get("key", "").strip()
            if not key or len(key) < 8:
                return jsonify({"error": "Ključ je prekratak (min 8 znakova)"}), 400

            prov_u = provider.upper()
            cfg_path = Path("dev_api.json")

            # Učitaj postojeću konfiguraciju
            try:
                cfg = json.loads(cfg_path.read_text("utf-8"))
            except Exception:
                cfg = {}

            # Dodaj ključ
            if prov_u not in cfg:
                cfg[prov_u] = []
            if isinstance(cfg[prov_u], list):
                if key not in cfg[prov_u]:
                    cfg[prov_u].append(key)
            elif isinstance(cfg[prov_u], dict):
                cfg[prov_u][f"key_{len(cfg[prov_u])+1}"] = key

            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")

            # Reload fleet
            _get_fleet().reload()

            return jsonify({"ok": True, "provider": prov_u})
        except Exception as e:
            print("api/keys greska:", traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    @app.route("/api/keys/<provider>/<int:index>", methods=["DELETE"])
    def api_keys_delete(provider, index):
        """Briše API ključ po indeksu."""
        try:
            prov_u = provider.upper()
            cfg_path = Path("dev_api.json")

            cfg = json.loads(cfg_path.read_text("utf-8"))
            if prov_u not in cfg or not isinstance(cfg[prov_u], list):
                return jsonify({"error": "Provajder nije pronađen"}), 404
            if index >= len(cfg[prov_u]):
                return jsonify({"error": "Index van granica"}), 400

            removed = cfg[prov_u].pop(index)
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
            _get_fleet().reload()

            return jsonify({"ok": True, "removed": removed[:8] + "..."})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # FLEET — /api/fleet (ovdje radi kao override)
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/fleet")
    def api_fleet():
        try:
            return jsonify(_get_fleet().get_fleet_ui())
        except Exception as e:
            print("api/fleet greska:", traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fleet/toggle", methods=["POST"])
    def api_fleet_toggle():
        try:
            data = request.get_json(force=True) or {}
            provider = data.get("provider", "").upper()
            key = data.get("key", "")
            if not provider or not key:
                return jsonify({"error": "Nedostaje provider ili key"}), 400
            return jsonify(_get_fleet().toggle_key(provider, key))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # DOWNLOAD — /api/download, /api/download_live
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/download")
    def api_download():
        out = SHARED_STATS.get("output_file")
        if not out or not Path(out).exists():
            # Pokušaj pronaći zadnji PREVEDENO_ fajl
            candidates = sorted(Path(INPUT_DIR).glob("PREVEDENO_*.epub"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                return jsonify({"error": "Nema fajla za preuzimanje"}), 404
            out = str(candidates[0])
        return send_file(out, as_attachment=True)

    @app.route("/api/download_live")
    def api_download_live():
        candidates = sorted(Path(INPUT_DIR).glob("(LIVE)_*.epub"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return jsonify({"error": "Nema live preview fajla"}), 404
        return send_file(str(candidates[0]), as_attachment=True)

    # ═════════════════════════════════════════════════════════════════════════
    # BLUEPRINT-I (opcionalno — ne ruše server ako ne postoje)
    # ═════════════════════════════════════════════════════════════════════════

    try:
        from api import register_blueprints
        from api.middleware import register_error_handlers
        register_blueprints(app)
        register_error_handlers(app)
        print("✅ Blueprint-i učitani")
    except ImportError as e:
        print(f"ℹ️  Blueprint import preskočen ({e}) — sve rute su definirane direktno")
    except Exception as e:
        print(f"⚠️  Blueprint greška: {e}")

    return app


# ── Pokretanje ────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    try:
        from config.settings import PORT
    except ImportError:
        PORT = 8080

    print(f"🚀 BOOKLYFI server: http://127.0.0.1:{PORT}")
    # FIX: config je već postavljen u create_app(), ovo je samo za sigurnost
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
