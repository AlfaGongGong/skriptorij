import os
import json
import re
import threading
import traceback
from pathlib import Path
from flask import (
    Flask, make_response, redirect, render_template,
    request, jsonify, send_file,
)
from api_fleet import FleetManager

# ── Fleet singleton ───────────────────────────────────────────────────────────
_fleet_fallback = FleetManager(config_path="dev_api.json")


def _get_fleet() -> FleetManager:
    import api_fleet as _af
    return _af._active_fleet if _af._active_fleet is not None else _fleet_fallback


# ── Shared state ─────────────────────────────────────────────────────────────
try:
    from config.settings import (
        SHARED_STATS, SHARED_CONTROLS,
        INPUT_DIR, OUTPUT_DIR, SERVER_RUN_ID,
        CHECKPOINT_BASE_DIR,
    )
except ImportError:
    INPUT_DIR  = Path("data")
    OUTPUT_DIR = Path("data")
    SERVER_RUN_ID = "dev"
    CHECKPOINT_BASE_DIR = Path("data/_checkpoints")
    SHARED_STATS: dict = {
        "status": "IDLE", "pct": 0, "ok": "0 / 0", "skipped": 0,
        "current_file": "", "active_engine": "---",
        "fleet_active": 0, "fleet_cooling": 0,
        "live_audit": "", "output_file": "", "output_dir": "data",
        "est": "--:--:--", "quality_scores": {}, "glosar_problemi": {},
        "knjiga_mode": None, "knjiga_mode_info": "",
    }
    SHARED_CONTROLS: dict = {"stop": False, "pause": False, "reset": False}

_engine_thread: threading.Thread | None = None


# ── Pomoćne ──────────────────────────────────────────────────────────────────

def _list_books() -> list[dict]:
    base = Path(INPUT_DIR)
    exts = {".epub", ".mobi"}
    books = []
    for p in sorted(base.glob("*")):
        if p.suffix.lower() in exts and not p.name.startswith("(LIVE)"):
            books.append({
                "name": p.name,
                "path": str(p),
                "size_bytes": p.stat().st_size,
            })
    return books


def _find_epub(name: str) -> Path | None:
    for base in [OUTPUT_DIR, INPUT_DIR]:
        p = Path(base) / name
        if p.exists():
            return p
    return None


def _latest_prevedeno() -> Path | None:
    candidates = []
    for base in [OUTPUT_DIR, INPUT_DIR]:
        candidates += list(Path(base).glob("PREVEDENO_*.epub"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _latest_live() -> Path | None:
    candidates = list(Path(INPUT_DIR).glob("(LIVE)_*.epub"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _get_checkpoint_count(book_path: Path) -> tuple[int, Path | None]:
    """Vraća (broj_checkpointa, checkpoint_dir) za datu knjigu iz CHECKPOINT_BASE_DIR."""
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-čćžšđČĆŽŠĐ]", "_", book_path.stem)
    clean_stem_safe = re.sub(r"[^a-zA-Z0-9_\-]", "", book_path.stem)

    # Pokušaj u CHECKPOINT_BASE_DIR (nova putanja)
    for stem in (clean_stem_safe, clean_stem):
        work_dir = CHECKPOINT_BASE_DIR / f"_skr_{stem}"
        if work_dir.exists():
            checkpoint_dir = work_dir / "checkpoints"
            count = len(list(checkpoint_dir.glob("*.chk"))) if checkpoint_dir.exists() else 0
            return count, checkpoint_dir

    # Fuzzy
    candidates = list(CHECKPOINT_BASE_DIR.glob(f"_skr_{clean_stem_safe[:10]}*"))
    if candidates:
        work_dir = candidates[0]
        checkpoint_dir = work_dir / "checkpoints"
        count = len(list(checkpoint_dir.glob("*.chk"))) if checkpoint_dir.exists() else 0
        return count, checkpoint_dir

    return 0, None


def _obrisi_checkpoint_i_kes(book: str) -> dict:
    """Briše cijeli _skr_ direktorij za datu knjigu."""
    from utils.checkpoint_cleaner import full_reset
    stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(book).stem)
    return full_reset(stem)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> Flask:
    os.makedirs(INPUT_DIR, exist_ok=True)
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except OSError:
        pass

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

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
    # KNJIGE
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/books")
    @app.route("/api/files")
    def api_books():
        try:
            books = _list_books()
            return jsonify({"books": books, "files": [b["name"] for b in books]})
        except Exception as e:
            return jsonify({"error": str(e), "books": [], "files": []}), 500

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
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # MODELI
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/dev_models")
    def api_dev_models():
        try:
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
                    for prov in [
                        "GEMINI", "GROQ", "CEREBRAS", "MISTRAL", "SAMBANOVA",
                        "TOGETHER", "OPENROUTER", "COHERE", "CHUTES",
                        "HUGGINGFACE", "KLUSTER", "FIREWORKS", "GEMMA",
                    ]:
                        if prov in has_keys:
                            models.append(prov)
            except Exception:
                pass
            if not models:
                models = ["V10_TURBO", "V8_TURBO", "GEMINI", "GROQ", "MISTRAL"]
            return jsonify(models)
        except Exception:
            return jsonify(["V10_TURBO", "V8_TURBO"]), 200

    # ═════════════════════════════════════════════════════════════════════════
    # STATUS
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/status")
    def api_status():
        try:
            fleet = _get_fleet()
            summary = fleet.get_fleet_summary()
            active_keys  = sum(v["active"]  for v in summary.values())
            cooling_keys = sum(v["cooling"] for v in summary.values())

            raw_qs = SHARED_STATS.get("quality_scores", {})
            normalized_qs: dict[str, float] = {}
            for k, v in raw_qs.items():
                if isinstance(v, (int, float)):
                    normalized_qs[k] = float(v)
                elif isinstance(v, dict) and "score" in v:
                    normalized_qs[k] = float(v["score"])

            return jsonify({
                **SHARED_STATS,
                "quality_scores": normalized_qs,
                "fleet_active":   active_keys,
                "fleet_cooling":  cooling_keys,
                "output_dir":     str(OUTPUT_DIR),
            })
        except Exception as e:
            return jsonify({**SHARED_STATS, "error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # CHECKPOINTS
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/checkpoints")
    def api_checkpoints():
        try:
            book = request.args.get("book", "").strip()
            if not book:
                return jsonify({"count": 0})

            book_path = (
                Path(book) if Path(book).is_absolute()
                else Path(INPUT_DIR) / book
            )
            count, checkpoint_dir = _get_checkpoint_count(book_path)

            return jsonify({
                "count": count,
                "book": book_path.stem,
                "checkpoint_dir": str(checkpoint_dir) if checkpoint_dir else None,
            })
        except Exception as e:
            return jsonify({"count": 0, "error": str(e)}), 200

    # ═════════════════════════════════════════════════════════════════════════
    # QUALITY SCORES
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/quality")
    def api_quality():
        scores_raw = SHARED_STATS.get("quality_scores", {})

        if not scores_raw:
            try:
                skr_dirs = sorted(
                    CHECKPOINT_BASE_DIR.glob("_skr_*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if skr_dirs:
                    qs_file = skr_dirs[0] / "checkpoints" / "quality_scores.json"
                    if qs_file.exists():
                        scores_raw = json.loads(qs_file.read_text("utf-8"))
            except Exception:
                pass

        scores: dict[str, float] = {}
        for k, v in scores_raw.items():
            if isinstance(v, (int, float)):
                scores[k] = float(v)
            elif isinstance(v, dict) and "score" in v:
                scores[k] = float(v["score"])

        vals = list(scores.values())
        prosjek = round(sum(vals) / len(vals), 2) if vals else None
        losi = {k: v for k, v in scores.items() if v < 6.5}

        return jsonify({
            "scores": scores,
            "loši_blokovi": losi,
            "statistike": {
                "prosječan": prosjek,
                "ukupno": len(scores),
                "loših": len(losi),
            },
            "glosar_problemi": SHARED_STATS.get("glosar_problemi", {}),
        })

    @app.route("/api/quality_scores")
    def api_quality_scores():
        try:
            scores_raw = SHARED_STATS.get("quality_scores", {})

            if not scores_raw:
                try:
                    output_file = SHARED_STATS.get("output_file", "")
                    if output_file:
                        stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(output_file).stem)
                        qs_candidate = CHECKPOINT_BASE_DIR / f"_skr_{stem}" / "checkpoints" / "quality_scores.json"
                        if qs_candidate.exists():
                            scores_raw = json.loads(qs_candidate.read_text("utf-8"))

                    if not scores_raw:
                        skr_dirs = sorted(
                            CHECKPOINT_BASE_DIR.glob("_skr_*"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        if skr_dirs:
                            qs_file = skr_dirs[0] / "checkpoints" / "quality_scores.json"
                            if qs_file.exists():
                                scores_raw = json.loads(qs_file.read_text("utf-8"))
                except Exception:
                    pass

            scores: dict[str, float] = {}
            for k, v in scores_raw.items():
                if isinstance(v, (int, float)):
                    scores[k] = float(v)
                elif isinstance(v, dict) and "score" in v:
                    scores[k] = float(v["score"])

            if not scores:
                return jsonify({
                    "scores": {}, "by_file": {}, "has_data": False, "summary": {},
                    "message": "Nema quality scores podataka. Pokreni obradu prvo."
                })

            vals = list(scores.values())
            n = len(vals)
            excellent = sum(1 for v in vals if v >= 8.5)
            good      = sum(1 for v in vals if 6.5 <= v < 8.5)
            poor      = sum(1 for v in vals if 4.0 <= v < 6.5)
            critical  = sum(1 for v in vals if v < 4.0)
            avg       = round(sum(vals) / n, 2)

            by_file: dict = {}
            for stem, score in sorted(scores.items()):
                parts = stem.split("_blok_")
                fn = parts[0] if len(parts) == 2 else stem
                if fn not in by_file:
                    by_file[fn] = {"blocks": [], "total": 0.0, "count": 0}
                by_file[fn]["blocks"].append({"stem": stem, "score": round(score, 1)})
                by_file[fn]["total"] += score
                by_file[fn]["count"] += 1

            for fn in by_file:
                cnt = by_file[fn]["count"]
                by_file[fn]["avg"] = round(by_file[fn]["total"] / cnt, 2) if cnt else 0.0
                del by_file[fn]["total"]

            return jsonify({
                "scores":   scores,
                "by_file":  by_file,
                "has_data": True,
                "summary":  {
                    "avg": avg, "min": round(min(vals), 1), "max": round(max(vals), 1),
                    "total": n, "excellent": excellent, "good": good,
                    "poor": poor, "critical": critical,
                    "pct_print_ready": round((excellent / n) * 100, 1),
                },
                "losi_blokovi": {k: v for k, v in scores.items() if v < 6.5},
            })
        except Exception as e:
            return jsonify({"error": str(e), "has_data": False}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # SAVE SCORES
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/save_scores", methods=["POST"])
    def api_save_scores():
        try:
            qs = SHARED_STATS.get("quality_scores", {})
            if not qs:
                return jsonify({"ok": False, "error": "Nema quality scores u memoriji."}), 400

            current_file = SHARED_STATS.get("current_file", "")
            if not current_file:
                return jsonify({"ok": False, "error": "Nije poznata aktivna knjiga."}), 400

            stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(current_file).stem)
            qs_dir = CHECKPOINT_BASE_DIR / f"_skr_{stem}" / "checkpoints"

            if not qs_dir.exists():
                skr_dirs = sorted(
                    CHECKPOINT_BASE_DIR.glob("_skr_*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if skr_dirs:
                    qs_dir = skr_dirs[0] / "checkpoints"

            qs_dir.mkdir(parents=True, exist_ok=True)
            qs_path = qs_dir / "quality_scores.json"

            normalized = {}
            for k, v in qs.items():
                if isinstance(v, (int, float)):
                    normalized[k] = float(v)
                elif isinstance(v, dict) and "score" in v:
                    normalized[k] = float(v["score"])

            qs_path.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            return jsonify({"ok": True, "saved": len(normalized), "path": str(qs_path)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # START — auto-detekcija moda, bez mode parametra
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/start", methods=["POST"])
    def api_start():
        global _engine_thread
        try:
            data  = request.get_json(force=True) or {}
            book  = data.get("book",  "").strip()
            model = data.get("model", "V10_TURBO").strip()
            # mode parametar se ignorira — engine sam detektuje

            if not book:
                return jsonify({"error": "Nedostaje 'book' parametar"}), 400

            book_path = (
                Path(book) if Path(book).is_absolute()
                else Path(INPUT_DIR) / book
            )
            if not book_path.exists():
                found = list(Path(INPUT_DIR).glob(f"**/{book_path.name}"))
                if not found:
                    return jsonify({"error": f"Knjiga nije pronađena: {book}"}), 404
                book_path = found[0]

            if SHARED_STATS.get("status", "IDLE") not in ("IDLE", "ZAUSTAVLJENO", "GREŠKA", "ZAVRŠENO"):
                if _engine_thread and _engine_thread.is_alive():
                    return jsonify({"error": "Obrada je već u toku. Zaustavi je prvo."}), 409

            SHARED_CONTROLS["stop"]  = False
            SHARED_CONTROLS["pause"] = False

            chk_count, _ = _get_checkpoint_count(book_path)
            has_checkpoints = chk_count > 0

            SHARED_STATS.update({
                "status":          "POKRETANJE...",
                "pct":             SHARED_STATS.get("pct", 0) if has_checkpoints else 0,
                "ok":              SHARED_STATS.get("ok", "0 / 0") if has_checkpoints else "0 / 0",
                "skipped":         0,
                "current_file":    "",
                "active_engine":   model,
                "live_audit":      "💾 Nastavljam od checkpointa..." if has_checkpoints else "",
                "output_file":     SHARED_STATS.get("output_file") if has_checkpoints else "",
                "output_dir":      str(OUTPUT_DIR),
                "est":             "--:--:--",
                "quality_scores":  SHARED_STATS.get("quality_scores", {}) if has_checkpoints else {},
                "glosar_problemi": {},
                "knjiga_mode":     None,
                "knjiga_mode_info": "",
            })

            mode = data.get("tool", data.get("mode", "")).strip().upper()

            def run_engine():
                try:
                    if mode == "RETRO":
                        import asyncio
                        from core.engine import SkriptorijAllInOne
                        from processing.retro import retroaktivna_relektura_v10
                        engine = SkriptorijAllInOne(
                            str(book_path), model, SHARED_STATS, SHARED_CONTROLS
                        )
                        engine.work_dir.mkdir(parents=True, exist_ok=True)
                        engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)
                        SHARED_STATS["status"] = "RETRO RE-LEKTURA"
                        SHARED_STATS["pct"] = 0
                        asyncio.run(retroaktivna_relektura_v10(
                            engine,
                            force=False,
                            only_bad=True,
                            bad_threshold=6.5,
                        ))
                        SHARED_STATS["status"] = "ZAVRŠENO (RETRO)"
                        SHARED_STATS["pct"] = 100

                    elif mode == "REFIX":
                        # ── Selektivna relektura označenih blokova ────────────
                        import asyncio
                        from core.engine import SkriptorijAllInOne
                        from processing.retro import retroaktivna_relektura_v10

                        stems = SHARED_CONTROLS.get("refix_stems", [])
                        if not stems:
                            SHARED_STATS["status"] = "GREŠKA: nema označenih blokova"
                            return

                        engine = SkriptorijAllInOne(
                            str(book_path), model, SHARED_STATS, SHARED_CONTROLS
                        )
                        engine.work_dir.mkdir(parents=True, exist_ok=True)
                        engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

                        n = len(stems)
                        engine.log(
                            f"🔧 Selektivna relektura: {n} blokova → {stems[:5]}{'...' if n>5 else ''}",
                            "system"
                        )

                        # stems_whitelist filtrira samo označene blokove (patch u retro.py)
                        asyncio.run(retroaktivna_relektura_v10(
                            engine,
                            stems_whitelist=stems,
                        ))

                        SHARED_CONTROLS.pop("refix_stems", None)
                        SHARED_CONTROLS.pop("refix_book",  None)
                        SHARED_STATS["status"] = f"ZAVRŠENO (REFIX {n} blokova)"
                        SHARED_STATS["pct"] = 100

                    else:
                        from run import start_skriptorij_from_master
                        start_skriptorij_from_master(
                            str(book_path), model, SHARED_STATS, SHARED_CONTROLS
                        )
                except Exception as exc:
                    print("Engine greska:", traceback.format_exc())
                    SHARED_STATS["status"] = f"GREŠKA: {type(exc).__name__}"
                    SHARED_STATS["live_audit"] += f"\nGreska: {exc}"

            _engine_thread = threading.Thread(
                target=run_engine, daemon=True, name="booklyfi-engine"
            )
            _engine_thread.start()

            return jsonify({
                "ok":    True,
                "book":  book_path.name,
                "model": model,
                "mode":  "AUTO",
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # KONTROLA — reset briše checkpoint + keš
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
                SHARED_CONTROLS["stop"]  = True
                SHARED_CONTROLS["pause"] = False
                SHARED_STATS["status"]   = "ZAUSTAVLJENO"
            elif action == "reset":
                SHARED_CONTROLS["stop"]  = True
                SHARED_CONTROLS["pause"] = False
                SHARED_CONTROLS["reset"] = True

                active_book = SHARED_STATS.get("current_file", "")
                reset_result = {}
                if active_book:
                    reset_result = _obrisi_checkpoint_i_kes(active_book)

                SHARED_STATS.update({
                    "status": "IDLE", "pct": 0, "ok": "0 / 0",
                    "skipped": 0, "current_file": "", "active_engine": "---",
                    "live_audit": "", "output_file": "",
                    "quality_scores": {}, "glosar_problemi": {},
                    "knjiga_mode": None, "knjiga_mode_info": "",
                })
                return jsonify({"ok": True, "action": action, "reset": reset_result})
            else:
                return jsonify({"error": f"Nepoznata akcija: {action}"}), 400
            return jsonify({"ok": True, "action": action})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # API RESET FULL — novi endpoint
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/reset_full", methods=["POST"])
    def api_reset_full():
        """
        Potpuni reset za zadanu knjigu:
          - Briše checkpoint direktorij + keš (book_analysis.json, quality_scores.json, .chk)
          - Resetuje SHARED_STATS
        Body: {"book": "ime.epub"}
        """
        try:
            data = request.get_json(force=True) or {}
            book = data.get("book", "").strip()
            if not book:
                return jsonify({"error": "Nedostaje parametar 'book'"}), 400

            SHARED_CONTROLS["stop"]  = True
            SHARED_CONTROLS["pause"] = False
            SHARED_CONTROLS["reset"] = True

            reset_result = _obrisi_checkpoint_i_kes(book)

            SHARED_STATS.update({
                "status":       "IDLE",
                "pct":          0,
                "ok":           "0 / 0",
                "skipped":      0,
                "current_file": "",
                "active_engine": "---",
                "live_audit":   "Sistem u potpunosti resetovan.\n",
                "output_file":  "",
                "quality_scores": {},
                "glosar_problemi": {},
                "knjiga_mode":  None,
                "knjiga_mode_info": "",
            })
            return jsonify({
                "ok":    reset_result.get("ok", False),
                "book":  book,
                "reset": reset_result,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # API KLJUČEVI
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/keys")
    def api_keys_get():
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
        try:
            data = request.get_json(force=True) or {}
            key  = data.get("key", "").strip()
            if not key or len(key) < 8:
                return jsonify({"error": "Ključ je prekratak (min 8 znakova)"}), 400
            prov_u   = provider.upper()
            cfg_path = Path("dev_api.json")
            try:
                cfg = json.loads(cfg_path.read_text("utf-8"))
            except Exception:
                cfg = {}
            if prov_u not in cfg:
                cfg[prov_u] = []
            if isinstance(cfg[prov_u], list):
                if key not in cfg[prov_u]:
                    cfg[prov_u].append(key)
            elif isinstance(cfg[prov_u], dict):
                cfg[prov_u][f"key_{len(cfg[prov_u])+1}"] = key
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
            _get_fleet().reload()
            return jsonify({"ok": True, "provider": prov_u})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/keys/<provider>/<int:index>", methods=["DELETE"])
    def api_keys_delete(provider, index):
        try:
            prov_u   = provider.upper()
            cfg_path = Path("dev_api.json")
            cfg      = json.loads(cfg_path.read_text("utf-8"))
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
    # FLEET
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/fleet")
    def api_fleet():
        try:
            return jsonify(_get_fleet().get_fleet_ui())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fleet/toggle", methods=["POST"])
    def api_fleet_toggle():
        try:
            data     = request.get_json(force=True) or {}
            provider = data.get("provider", "").upper()
            key      = data.get("key", "")
            if not provider or not key:
                return jsonify({"error": "Nedostaje provider ili key"}), 400
            return jsonify(_get_fleet().toggle_key(provider, key))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # DOWNLOAD
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/download")
    def api_download():
        try:
            output_file = SHARED_STATS.get("output_file", "")
            target = None

            if output_file:
                p = Path(output_file)
                if p.exists():
                    target = p
                else:
                    target = _find_epub(p.name)

            if target is None:
                target = _latest_prevedeno()

            if target is None or not target.exists():
                return jsonify({"error": "Nema završenog EPUB fajla"}), 404

            return send_file(
                target,
                as_attachment=True,
                download_name=target.name,
                mimetype="application/epub+zip",
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/download_live")
    def api_download_live():
        try:
            target = _latest_live()
            if target is None or not target.exists():
                return jsonify({"error": "Nema live EPUB fajla"}), 404
            return send_file(
                target,
                as_attachment=True,
                download_name=target.name,
                mimetype="application/epub+zip",
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # REVIEW — lista blokova za relekturu + označavanje za REFIX
    # ═════════════════════════════════════════════════════════════════════════

    @app.route("/api/review/list")
    def api_review_list():
        """
        Vraća listu blokova označenih za ljudsku reviziju iz human_review.json.
        Čita iz najnovijeg _skr_ direktorija (ili onog koji odgovara aktivnoj knjizi).
        """
        try:
            review_path = None

            # Pokušaj pronaći direktorij aktivne knjige
            current_file = SHARED_STATS.get("current_file", "")
            if current_file:
                stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(current_file).stem)
                candidate = CHECKPOINT_BASE_DIR / f"_skr_{stem}" / "checkpoints" / "human_review.json"
                if candidate.exists():
                    review_path = candidate

            # Fallback: najnoviji _skr_ direktorij
            if review_path is None:
                skr_dirs = sorted(
                    CHECKPOINT_BASE_DIR.glob("_skr_*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for skr in skr_dirs:
                    candidate = skr / "checkpoints" / "human_review.json"
                    if candidate.exists():
                        review_path = candidate
                        break

            if review_path is None:
                return jsonify([])

            items = json.loads(review_path.read_text("utf-8"))

            # Normalizacija: osiguraj da svaki item ima i "stem" i "file" polje
            for item in items:
                file_val = item.get("file", "")
                stem_val = item.get("stem", "")
                if not stem_val and file_val:
                    item["stem"] = file_val[:-4] if file_val.endswith(".chk") else file_val
                if not file_val and stem_val:
                    item["file"] = stem_val + ".chk"

            # Dodaj info koji stemovi su već označeni za REFIX
            marked = set(SHARED_CONTROLS.get("refix_stems", []))
            for item in items:
                item["marked"] = item.get("stem", "") in marked

            # Vraćamo direktno array — frontend radi items.map() bez .items property
            return jsonify(items)
        except Exception as e:
            return jsonify({"error": str(e)}), 500  # 500 sa errorom je ok, frontend ga hvata

    @app.route("/api/review/mark", methods=["POST"])
    def api_review_mark():
        """
        Označava blokove za selektivnu REFIX relekturu.
        Body: {"book": "ime.epub", "stems": ["chapter056.html_blok_0", ...]}
        Nakon ovoga pokreni /api/start s tool=REFIX.
        """
        try:
            data  = request.get_json(force=True) or {}
            stems = data.get("stems", [])
            book  = data.get("book", "").strip()

            if not isinstance(stems, list) or not stems:
                return jsonify({"error": "Nedostaje 'stems' lista (mora biti neprazan niz)"}), 400

            SHARED_CONTROLS["refix_stems"] = [str(s) for s in stems]
            if book:
                SHARED_CONTROLS["refix_book"] = book

            return jsonify({
                "ok": True,
                "marked": len(stems),
                "stems": stems,
                "book": book or SHARED_CONTROLS.get("refix_book", ""),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/review/clear", methods=["POST"])
    def api_review_clear():
        """Briše označene stemove iz SHARED_CONTROLS (nakon završenog REFIX-a)."""
        try:
            SHARED_CONTROLS.pop("refix_stems", None)
            SHARED_CONTROLS.pop("refix_book",  None)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════════════
    # REVIEW — GET i POST za pojedinačni chunk (.chk fajl)
    # GET  /api/review/chunk/<stem>  → vraća tekst iz .chk fajla
    # POST /api/review/chunk/<stem>  → upisuje izmijenjeni tekst u .chk fajl
    # ═════════════════════════════════════════════════════════════════════════

    def _find_chk_path(stem: str) -> Path | None:
        """
        Traži .chk fajl za dati stem u svim _skr_ direktorijima.
        stem može biti:
          - 'chapter056.html_blok_0'          (bez .chk)
          - 'chapter056.html_blok_0.chk'      (s ekstenzijom)
        """
        # Normaliziraj: ukloni .chk sufiks ako ga ima
        clean = stem[:-4] if stem.endswith(".chk") else stem

        # Pokušaj direktno iz aktivne knjige
        current_file = SHARED_STATS.get("current_file", "")
        if current_file:
            book_stem = re.sub(r"[^a-zA-Z0-9_\-]", "", Path(current_file).stem)
            candidate = CHECKPOINT_BASE_DIR / f"_skr_{book_stem}" / "checkpoints" / f"{clean}.chk"
            if candidate.exists():
                return candidate

        # Pretraži sve _skr_ direktorije (najnoviji prvi)
        skr_dirs = sorted(
            CHECKPOINT_BASE_DIR.glob("_skr_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for skr in skr_dirs:
            candidate = skr / "checkpoints" / f"{clean}.chk"
            if candidate.exists():
                return candidate

        return None

    @app.route("/api/review/chunk/<path:stem>", methods=["GET"])
    def api_review_chunk_get(stem):
        """
        Vraća tekst prevoda iz .chk fajla za dati stem.
        Odgovor: {"stem": str, "text": str, "path": str}
        """
        try:
            chk_path = _find_chk_path(stem)
            if chk_path is None:
                return jsonify({"error": f"Chunk nije pronađen: {stem}", "text": ""}), 404

            raw = chk_path.read_text("utf-8", errors="replace")

            # .chk fajlovi mogu biti plain tekst ili JSON {"translated": "..."}
            text = raw
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    # Pokušaj uobičajene ključeve
                    text = (
                        obj.get("translated")
                        or obj.get("text")
                        or obj.get("content")
                        or obj.get("output")
                        or raw
                    )
            except (json.JSONDecodeError, ValueError):
                pass  # plain tekst, OK

            return jsonify({
                "stem": stem,
                "text": text,
                "path": str(chk_path),
            })
        except Exception as e:
            return jsonify({"error": str(e), "text": ""}), 500

    @app.route("/api/review/chunk/<path:stem>", methods=["POST"])
    def api_review_chunk_post(stem):
        """
        Upisuje izmijenjeni tekst prevoda u .chk fajl.
        Body: {"text": "novi tekst prevoda"}
        """
        try:
            chk_path = _find_chk_path(stem)
            if chk_path is None:
                return jsonify({"error": f"Chunk nije pronađen: {stem}"}), 404

            data = request.get_json(force=True) or {}
            new_text = data.get("text", "")
            if not isinstance(new_text, str):
                return jsonify({"error": "'text' mora biti string"}), 400

            raw = chk_path.read_text("utf-8", errors="replace")

            # Sačuvaj u istom formatu kao originalni fajl
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    # Ažuriraj odgovarajući ključ
                    for key in ("translated", "text", "content", "output"):
                        if key in obj:
                            obj[key] = new_text
                            break
                    else:
                        obj["translated"] = new_text
                    chk_path.write_text(
                        json.dumps(obj, ensure_ascii=False, indent=2), "utf-8"
                    )
                else:
                    chk_path.write_text(new_text, "utf-8")
            except (json.JSONDecodeError, ValueError):
                # Plain tekst fajl
                chk_path.write_text(new_text, "utf-8")

            return jsonify({"ok": True, "stem": stem, "path": str(chk_path)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route("/api/epub_preview", methods=["GET"])
    def epub_preview():
        """Plain text iz .chk fajlova aktivne knjige."""
        from flask import Response
        import json as _json

        try:
            book = SHARED_STATS.get("current_file", "") or SHARED_STATS.get("output_file", "")

            if not book:
                lbp = Path(INPUT_DIR) / "last_book.json"
                if lbp.exists():
                    try:
                        book = _json.loads(lbp.read_text("utf-8")).get("last_book", "")
                    except Exception:
                        pass

            if not book:
                return Response("Nema aktivne knjige.", mimetype="text/plain")

            clean = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
            chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

            if not chk_dir.exists():
                candidates = sorted(
                    CHECKPOINT_BASE_DIR.glob(f"_skr_{clean[:10]}*"),
                    key=lambda p: p.stat().st_mtime, reverse=True
                )
                if candidates:
                    chk_dir = candidates[0] / "checkpoints"

            if not chk_dir.exists():
                svi = sorted(
                    CHECKPOINT_BASE_DIR.glob("_skr_*"),
                    key=lambda p: p.stat().st_mtime, reverse=True
                )
                if svi:
                    chk_dir = svi[0] / "checkpoints"

            if not chk_dir.exists():
                return Response("Nema checkpointa za ovu knjigu.", mimetype="text/plain")

            chk_files = sorted(
                f for f in chk_dir.glob("*.chk")
                if not any(f.name.endswith(s) for s in (".prevod.chk", ".lektura.chk"))
            )

            if not chk_files:
                return Response("Obrada u toku — nema jos sacuvanih blokova.", mimetype="text/plain")

            dijelovi = []
            for chk in chk_files:
                try:
                    t = chk.read_text("utf-8", errors="ignore").strip()
                    if t:
                        dijelovi.append(t)
                except Exception:
                    continue

            if not dijelovi:
                return Response("Checkpointi su prazni.", mimetype="text/plain")

            return Response("\n\n".join(dijelovi), mimetype="text/plain; charset=utf-8")

        except Exception as e:
            return Response(f"Greska: {e}", mimetype="text/plain")

    return app

app = create_app()
