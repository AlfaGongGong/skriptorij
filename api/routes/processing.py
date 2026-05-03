"""
Rute za upravljanje obradom knjiga (files, start, status, modeli).
Dio Skriptorij V10 Turbo Omni-Core sistema.
"""

import json
import os
import re
import threading
import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import (
    PROJECTS_ROOT,
    SHARED_STATS,
    SHARED_CONTROLS,
    CONFIG_PATH,
    INPUT_DIR,
    CHECKPOINT_BASE_DIR,
)

bp = Blueprint("processing", __name__)

# Globalno praćenje vremena za ETA računanje
_start_time: float | None = None
_start_pct: float = 0

# ============================================================================
# POMOĆNE FUNKCIJE
# ============================================================================


def _racunaj_eta() -> str:
    """Računa preostalo vrijeme na osnovu prosječne brzine od starta."""
    pct = SHARED_STATS.get("pct", 0)
    if not _start_time or pct <= _start_pct or pct >= 100:
        return "--:--:--"
    elapsed = time.time() - _start_time
    done_pct = pct - _start_pct
    if done_pct <= 0:
        return "--:--:--"
    total_est = elapsed / (done_pct / 100.0)
    remaining = total_est - elapsed
    if remaining < 0:
        return "Uskoro..."
    h = int(remaining // 3600)
    m = int(remaining % 3600 // 60)
    s = int(remaining % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _get_checkpoint_count_base(book_path: Path) -> tuple[int, Path | None]:
    """
    Vraća (broj_checkpointa, checkpoint_dir) za datu knjigu.
    Traži u CHECKPOINT_BASE_DIR (nova putanja).
    """
    clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "", book_path.stem)
    work_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean_stem}"

    if not work_dir.exists():
        candidates = list(CHECKPOINT_BASE_DIR.glob(f"_skr_{clean_stem[:10]}*"))
        if candidates:
            work_dir = candidates[0]
        else:
            return 0, None

    checkpoint_dir = work_dir / "checkpoints"
    if not checkpoint_dir.exists():
        return 0, checkpoint_dir

    count = len(list(checkpoint_dir.glob("*.chk")))
    return count, checkpoint_dir


def _obrisi_checkpoint_i_kes(book: str) -> dict:
    """Briše cijeli _skr_ direktorij za datu knjigu iz CHECKPOINT_BASE_DIR."""
    from utils.checkpoint_cleaner import full_reset
    stem = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
    return full_reset(stem)


# ============================================================================
# API RUTE
# ============================================================================


@bp.route("/api/files")
def get_files():
    """Skenira INPUT_DIR i vraća listu dostupnih EPUB fajlova."""
    try:
        path = Path(INPUT_DIR)
        if not path.exists():
            return jsonify(
                {"error": "Putanja nije dostupna", "path": str(path), "files": []}
            ), 404

        files = [f.name for f in path.glob("*.epub")]
        return jsonify({"files": sorted(files)})
    except Exception as e:
        print(f" Greška pri skeniranju fajlova: {e}")
        return jsonify({"files": [], "error": str(e)}), 500


@bp.route("/api/dev_models")
def dev_models():
    """Čita modele iz dev_api.json — vraća provajdere + V8_TURBO opciju."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        models = ["V10_TURBO", "V8_TURBO"] + [
            k for k in data.keys() if k.upper() not in skip
        ]
        return jsonify(models)
    except Exception:
        return jsonify(["V10_TURBO", "GEMINI", "GROQ", "CEREBRAS"])


@bp.route("/api/status")
def get_status():
    """Vraća kompletan status s ETA računanjem."""
    SHARED_STATS["est"] = _racunaj_eta()
    return jsonify(SHARED_STATS)


@bp.route("/api/start", methods=["POST"])
def start_processing():
    """
    Pokretanje obrade.
    IZMJENA: 'mode' parametar se ignorira — engine sam detektuje mod putem
    _detect_knjiga_mode(). Ako postoje checkpointi → nastavlja; ako ne → počinje od nule.
    """
    global _start_time, _start_pct
    try:
        data = request.get_json()
        if not data or "book" not in data:
            return jsonify({"error": "Nije odabran fajl"}), 400

        book  = data["book"]
        model = data.get("model", "V10_TURBO")

        # Podržavamo tool (novi JS) i mode (stari JS) — ali samo RETRO i TTS
        # se prosljeđuju dalje; sve ostalo ide kroz auto-detekciju
        tool = data.get("tool", data.get("mode", "skriptorij")).upper()

        full_path = os.path.join(str(INPUT_DIR), book)
        if not os.path.exists(full_path):
            return jsonify(
                {"error": f"Fajl '{book}' ne postoji na lokaciji: {INPUT_DIR}"}
            ), 404

        SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})

        # Provjeri da li postoje checkpointi (nova putanja)
        chk_count, _ = _get_checkpoint_count_base(Path(full_path))
        has_checkpoints = chk_count > 0

        audit_entry = (
            f"💾 Nastavljam od checkpointa ({chk_count} blokova)...\n"
            if has_checkpoints
            else f"Sistem: Inicijalizacija auto-mode detekcije za: {book}\n"
        )
        SHARED_STATS.update({
            "status":          "POKRETANJE...",
            "current_file":    book,
            "active_engine":   model,
            "pct":             SHARED_STATS.get("pct", 0) if has_checkpoints else 0,
            "ok":              SHARED_STATS.get("ok", "0 / 0") if has_checkpoints else "0 / 0",
            "live_audit":      SHARED_STATS.get("live_audit", "") + audit_entry,
            "output_file":     SHARED_STATS.get("output_file") if has_checkpoints else "",
            "quality_scores":  SHARED_STATS.get("quality_scores", {}) if has_checkpoints else {},
            "glosar_problemi": {},
            "knjiga_mode":     None,   # engine postavlja
            "knjiga_mode_info": "",
        })

        _start_time = time.time()
        _start_pct  = 0

        try:
            with open(os.path.join(PROJECTS_ROOT, "last_book.json"), "w") as f:
                json.dump({"last_book": book}, f)
        except Exception:
            pass

        # Odabir modula: TTS, RETRO ili auto Prevod/Lektura
        if tool == "TTS":
            from tts import start_from_master as start_tts

            thread = threading.Thread(
                target=start_tts,
                args=(full_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )

        elif tool == "RETRO":
            import asyncio
            from processing.retro import retroaktivna_relektura_v10

            def _run_retro(fp=full_path, mdl=model):
                try:
                    from core.engine import SkriptorijAllInOne
                    engine = SkriptorijAllInOne(fp, mdl, SHARED_STATS, SHARED_CONTROLS)
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
                except Exception as exc:
                    import traceback as _tb
                    SHARED_STATS["status"] = f"RETRO GREŠKA: {exc}"
                    SHARED_STATS["live_audit"] = (
                        SHARED_STATS.get("live_audit", "") +
                        f"\n[RETRO ERROR] {_tb.format_exc()}"
                    )

            thread = threading.Thread(target=_run_retro, daemon=True)

        else:
            # AUTO-MODE: engine sam detektuje PREVOD / LEKTURA
            try:
                from run import start_skriptorij_from_master
            except ImportError:
                try:
                    from skriptorij import start_skriptorij_from_master
                except ImportError:

                    def start_skriptorij_from_master(*a, **kw):
                        raise RuntimeError("Nije pronađen ni run.py ni skriptorij.py!")

            thread = threading.Thread(
                target=start_skriptorij_from_master,
                args=(full_path, model, SHARED_STATS, SHARED_CONTROLS),
                daemon=True,
            )

        thread.start()
        return jsonify({
            "status": "Started",
            "file":   book,
            "tool":   tool,
            "mode":   "AUTO",   # engine automatski detektuje
            "has_checkpoints": has_checkpoints,
        })

    except Exception as e:
        err_msg = traceback.format_exc()
        SHARED_STATS["status"] = "KRITIČNA GREŠKA"
        SHARED_STATS["live_audit"] += (
            f"<div class='p-2 text-red-500'>Greška pri startu: {str(e)}</div>"
        )
        print(f"\n[BACKEND ERROR]\n{err_msg}\n")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/reset", methods=["POST"])
def reset_route():
    """
    Briše checkpointe i keš za aktivnu (ili zadanu) knjigu, resetuje SHARED_STATS.
    Body (opcionalno): {"book": "ime.epub"}
    """
    data = request.get_json(silent=True) or {}
    book = data.get("book") or SHARED_STATS.get("current_file", "")

    SHARED_CONTROLS["reset"] = True
    SHARED_CONTROLS["stop"]  = True

    reset_result = {}
    if book:
        reset_result = _obrisi_checkpoint_i_kes(book)

    SHARED_STATS.update({
        "pct":        0,
        "ok":         "0 / 0",
        "status":     "IDLE",
        "live_audit": "Sistem resetovan.\n",
        "quality_scores": {},
        "glosar_problemi": {},
        "knjiga_mode": None,
        "knjiga_mode_info": "",
    })
    return jsonify({"status": "reset", "reset": reset_result})


@bp.route("/api/reset_full", methods=["POST"])
def reset_full_route():
    """
    Potpuni reset: briše checkpoint dir + keš za zadanu knjugu.
    Body: {"book": "ime.epub"}  (obavezno)
    """
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


@bp.route("/api/debug/retro_check")
def debug_retro_check():
    """Privremeni endpoint — provjera da li je novi processing.py učitan."""
    import os, inspect
    src = inspect.getfile(debug_retro_check)
    mtime = os.path.getmtime(src)
    import datetime
    return jsonify({
        "file":     src,
        "modified": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "retro_supported":    True,
        "auto_mode_support":  True,
        "checkpoint_base":    str(CHECKPOINT_BASE_DIR),
        "version":            "v3_auto_mode",
    })


# ============================================================================
# PATCH v1.0 — Cache management & Review endpointi
# ============================================================================


@bp.route("/api/cache/clear", methods=["POST"])
def cache_clear():
    """
    Briše CIJELI cache (.chk fajlove) za aktivnu knjigu.
    POST body (opcionalno): {"book": "ime_knjige.epub"}
    """
    try:
        data = request.get_json(silent=True) or {}
        book = data.get("book") or SHARED_STATS.get("current_file", "")
        if not book:
            return jsonify({"error": "Nije odabrana knjiga"}), 400

        from core.engine import SkriptorijAllInOne
        engine = SkriptorijAllInOne(
            str(Path(INPUT_DIR) / book), "dummy", SHARED_STATS, SHARED_CONTROLS
        )
        obrisano = engine.obrisi_cache(samo_losi=False)
        return jsonify({
            "status":  "ok",
            "obrisano": obrisano,
            "poruka":  f"Obrisan kompletan cache: {obrisano} blokova",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/cache/clear_bad", methods=["POST"])
def cache_clear_bad():
    """
    Briše SAMO loše .chk fajlove (score ispod praga).
    POST body (opcionalno): {"book": "...", "threshold": 6.5}
    """
    try:
        data = request.get_json(silent=True) or {}
        book = data.get("book") or SHARED_STATS.get("current_file", "")
        threshold = float(data.get("threshold", 6.5))
        if not book:
            return jsonify({"error": "Nije odabrana knjiga"}), 400

        from core.engine import SkriptorijAllInOne
        engine = SkriptorijAllInOne(
            str(Path(INPUT_DIR) / book), "dummy", SHARED_STATS, SHARED_CONTROLS
        )
        obrisano = engine.obrisi_cache(samo_losi=True, threshold=threshold)
        return jsonify({
            "status":    "ok",
            "obrisano":  obrisano,
            "threshold": threshold,
            "poruka":    f"Obrisano {obrisano} loših blokova (score < {threshold})",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── FIX: Ispravljeni review endpointi ────────────────────────────────────────
# Promjene:
#   1. regex: r"[^a-zA-Z0-9_\-]" → r"[^a-zA-Z0-9_-]"  (uklonjen dvostruki backslash)
#   2. Koristi CHECKPOINT_BASE_DIR umjesto PROJECTS_ROOT za putanje
#   3. review_list: eksplicitno vraća jsonify([]) kad nema knjige — nikad HTML
#   4. review_chunk: sve greške vraćaju jsonify({}) — nikad HTML 404


def _resolve_chunk_path(chk_dir, stem: str):
    """
    FIX FAZA2 CHUNK: Pronalazi chunk fajl bez obzira na ekstenziju u stem-u.
    Stem može biti: "King_c43_r1.htm_blok_0" ili "King_c43_r1_blok_0"
    """
    from pathlib import Path
    chk_dir = Path(chk_dir)

    # 1. Direktno
    direct = _resolve_chunk_path(chk_dir, stem)
    if direct.exists():
        return direct

    # 2. Strip .htm/.html/.xhtml iz stem-a pa pokušaj
    clean_stem = re.sub(r"\.(x?html?)(_.+)?$", r"\2", stem, flags=re.IGNORECASE).lstrip("_")
    # Alternativa: ukloni samo file ekstenziju ispred _blok_
    clean_stem2 = re.sub(r"\.(x?html?)(_blok_)", r"\2", stem, flags=re.IGNORECASE)
    for s in (clean_stem, clean_stem2, stem.replace(".htm_", "_").replace(".html_", "_")):
        p = chk_dir / f"{s}.chk"
        if p.exists():
            return p

    # 3. Glob fallback — traži po blok broju
    blok_match = re.search(r"_blok_(\d+)$", stem)
    if blok_match:
        blok_num = blok_match.group(1)
        base_part = stem.split("_blok_")[0]
        # Ukloni .htm iz base_part
        base_clean = re.sub(r"\.(x?html?)$", "", base_part, flags=re.IGNORECASE)
        for pattern in (f"*{base_clean}*_blok_{blok_num}.chk",
                        f"*_blok_{blok_num}.chk"):
            matches = list(chk_dir.glob(pattern))
            if matches:
                return matches[0]

    return None

@bp.route("/api/review/list", methods=["GET"])
def review_list():
    """
    Vraća listu blokova označenih za ljudsku reviziju.

    PATCH: Sada merga dva izvora:
      1. human_review.json — blokovi koje je engine eksplicitno označio
      2. quality_scores.json — blokovi ispod threshold-a (default: 6.0)
         koji NISU označeni, ali ih treba prikazati korisniku

    Query param: ?threshold=6.0 (opcionalno, default 6.0)
    Uvijek vraća JSON — nikad HTML grešku.
    """
    try:
        threshold = float(request.args.get("threshold", 6.0))

        book = SHARED_STATS.get("current_file", "")
        if not book:
            last_book_path = Path(PROJECTS_ROOT) / "last_book.json"
            if last_book_path.exists():
                try:
                    book = json.loads(last_book_path.read_text("utf-8")).get("last_book", "")
                except Exception:
                    pass

        if not book:
            return jsonify([])

        clean = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
        chk_base = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        # ── Izvor 1: human_review.json ────────────────────────────────────────
        review_items = []
        seen_stems = set()

        review_path = chk_base / "human_review.json"
        if review_path.exists():
            try:
                raw = json.loads(review_path.read_text("utf-8"))
                items = raw if isinstance(raw, list) else []
                for item in items:
                    stem = item.get("stem") or item.get("file", "")
                    if stem and stem not in seen_stems:
                        seen_stems.add(stem)
                        # Osiguraj da item ima 'stem' polje
                        item.setdefault("stem", stem)
                        item.setdefault("source", "human_review")
                        review_items.append(item)
            except Exception:
                pass

        # ── Izvor 2: quality_scores.json — blokovi ispod threshold-a ─────────
        qs_path = chk_base / "quality_scores.json"
        if qs_path.exists():
            try:
                scores = json.loads(qs_path.read_text("utf-8"))
                for stem, score in sorted(scores.items()):
                    if stem in seen_stems:
                        continue  # Već u listi iz human_review
                    try:
                        score_f = float(score)
                    except (TypeError, ValueError):
                        continue
                    if score_f < threshold:
                        # Odredi file_name iz stem-a
                        parts = stem.split("_blok_")
                        file_name = parts[0] if len(parts) == 2 else stem
                        blok_num  = parts[1] if len(parts) == 2 else "?"

                        # Kreiraj review item za prikaz u UI
                        reason = _build_reason(score_f)
                        review_items.append({
                            "stem":    stem,
                            "file":    file_name,
                            "blok":    blok_num,
                            "score":   round(score_f, 1),
                            "reason":  reason,
                            "source":  "quality_scores",
                            "preview": "—"
                        })
                        seen_stems.add(stem)
            except Exception:
                pass

        # Sortiraj: najlošiji blokovi (niži score) idu naprijed
        review_items.sort(key=lambda x: float(x.get("score", 10.0)))

        return jsonify(review_items)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _build_reason(score: float) -> str:
    """Generiše kratki razlog za prikaz u Review tabu na osnovu ocjene."""
    if score < 2.0:
        return "Kritično: vjerovatno prazan ili neprevedeni blok"
    if score < 4.0:
        return f"Kritična ocjena ({score:.1f}/10) — potrebna ponovna obrada"
    if score < 6.0:
        return f"Loša ocjena ({score:.1f}/10) — preporučuje se ručna korektura"
    return f"Ocjena ispod praga ({score:.1f}/10)"


@bp.route("/api/review/chunk/<path:chunk_stem>", methods=["GET", "POST"])
def review_chunk(chunk_stem):
    """
    GET  — vraća tekst jednog .chk fajla za pregled/uređivanje.
    POST — sprema izmijenjeni tekst nazad u .chk fajl.
    Uvijek vraća JSON — nikad HTML grešku.
    """
    try:
        book = SHARED_STATS.get("current_file", "")
        if not book:
            last_book_path = Path(PROJECTS_ROOT) / "last_book.json"
            if last_book_path.exists():
                try:
                    book = json.loads(last_book_path.read_text("utf-8")).get("last_book", "")
                except Exception:
                    pass

        if not book:
            # FIX: jsonify umjesto abort(404) — abort vraća HTML stranicu
            return jsonify({"error": "Nema aktivne knjige. Odaberi knjigu pa pokušaj ponovo."}), 404

        # FIX: ispravljen regex — bez dvostrukog backslasha
        clean = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)

        # FIX: koristi CHECKPOINT_BASE_DIR (ispravna putanja)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        # Podržava i .chk ekstenziju i bez nje
        stem = chunk_stem.replace(".chk", "")
        chk_path = _resolve_chunk_path(chk_dir, stem)

        if request.method == "GET":
            if not chk_path.exists():
                return jsonify({"error": f"Chunk nije pronađen: {stem}"}), 404
            text = chk_path.read_text("utf-8", errors="ignore")
            return jsonify({"stem": stem, "text": text})

        elif request.method == "POST":
            data = request.get_json(silent=True) or {}
            new_text = data.get("text", "")
            if not new_text.strip():
                return jsonify({"error": "Prazan tekst"}), 400
            chk_path.parent.mkdir(parents=True, exist_ok=True)
            chk_path.write_text(new_text, encoding="utf-8")
            return jsonify({"status": "ok", "stem": stem})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/fix/bad_blocks", methods=["POST"])
def fix_bad_blocks():
    """
    Automatski ispravlja blokove s lošim scoreom:
      1. Briše njihove .chk fajlove
      2. Pokreće RETRO re-lekturu samo za te blokove
    POST body (opcionalno): {"book": "...", "threshold": 6.5}
    """
    try:
        data = request.get_json(silent=True) or {}
        book = data.get("book") or SHARED_STATS.get("current_file", "")
        threshold = float(data.get("threshold", 6.5))
        model = data.get("model", SHARED_STATS.get("active_engine", "V10_TURBO"))

        if not book:
            return jsonify({"error": "Nije odabrana knjiga"}), 400

        full_path = str(Path(INPUT_DIR) / book)
        if not Path(full_path).exists():
            return jsonify({"error": f"Fajl nije pronađen: {book}"}), 404

        SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})
        SHARED_STATS.update({
            "status":        "FIX LOŠIH BLOKOVA...",
            "current_file":  book,
            "active_engine": model,
            "pct":           0,
        })

        import asyncio
        import threading
        from processing.retro import send_to_fix

        def _run_fix():
            try:
                from core.engine import SkriptorijAllInOne
                engine = SkriptorijAllInOne(full_path, model, SHARED_STATS, SHARED_CONTROLS)
                SHARED_STATS["status"] = "FIX: BRISANJE LOŠEG CACHE-A..."
                asyncio.run(send_to_fix(engine, score_threshold=threshold))
                SHARED_STATS["status"] = "FIX ZAVRŠEN"
                SHARED_STATS["pct"] = 100
            except Exception as exc:
                import traceback as _tb
                SHARED_STATS["status"] = f"FIX GREŠKA: {exc}"
                SHARED_STATS["live_audit"] = (
                    SHARED_STATS.get("live_audit", "") +
                    f"\n[FIX ERROR] {_tb.format_exc()}"
                )

        thread = threading.Thread(target=_run_fix, daemon=True)
        thread.start()

        return jsonify({
            "status":    "Started",
            "book":      book,
            "threshold": threshold,
            "poruka":    f"Pokrenuto automatsko ispravljanje blokova s scoreom < {threshold}",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/api/admin/rebuild_review", methods=["POST"])
def rebuild_review():
    """Ručno pokreće mark_for_review za prvi checkpoint aktivne knjige."""
    import json as _json, os as _os
    from core.engine import SkriptorijAllInOne

    # 1. Odredi aktivnu knjigu iz SHARED_STATS ili last_book.json
    book = SHARED_STATS.get("current_file", "")
    if not book:
        lbp = Path(PROJECTS_ROOT) / "last_book.json"
        if lbp.exists():
            try:
                book = _json.loads(lbp.read_text()).get("last_book", "")
            except Exception:
                pass
    if not book:
        return jsonify({"error": "Nema aktivne knjige"}), 404

    book_path = str(Path(INPUT_DIR) / book)
    if not _os.path.exists(book_path):
        return jsonify({"error": f"Knjiga {book} ne postoji"}), 404

    # 2. Pokreni mark_for_review za prvi checkpoint
    try:
        eng = SkriptorijAllInOne(book_path, "dummy", SHARED_STATS, SHARED_CONTROLS)
        chk_list = sorted(eng.checkpoint_dir.glob("*.chk"))
        if not chk_list:
            return jsonify({"error": "Nema checkpointa"}), 400
        prvi = chk_list[0]

        if hasattr(eng, 'mark_for_review'):
            eng.mark_for_review(str(prvi))
        else:
            from core.processing import mark_for_review
            mark_for_review(str(prvi), eng)

        return jsonify({"status": "ok", "message": f"Review pokrenut za {prvi.name}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Učitaj human_review.json pri importu (ako postoji)
def _init_review_state():
    hr_path = None
    book = SHARED_STATS.get("current_file", "")
    if not book:
        lbp = Path(PROJECTS_ROOT) / "last_book.json"
        if lbp.exists():
            try:
                book = json.loads(lbp.read_text()).get("last_book", "")
            except Exception:
                pass
    if book:
        clean = re.sub(r'[^a-zA-Z0-9_\\-]', '', Path(book).stem)
        hr_path = Path(PROJECTS_ROOT) / f"_skr_{clean}" / "checkpoints" / "human_review.json"
    if hr_path and hr_path.exists():
        try:
            data = json.loads(hr_path.read_text("utf-8"))
            SHARED_STATS["current_file"] = data.get("file_path", "")
            SHARED_STATS["segments"] = data.get("segments", [])
        except Exception:
            pass

_init_review_state()

@bp.route("/api/epub_preview")
def epub_preview():
    """
    Vraća PLAIN TEXT iz svih obrađenih .chk fajlova aktivne knjige.
    Nikad ne vraća HTML grešku — uvijek text/plain.
    """
    from flask import Response

    try:
        book = SHARED_STATS.get("current_file", "") or SHARED_STATS.get("output_file", "")
        if not book:
            lbp = Path(PROJECTS_ROOT) / "last_book.json"
            if lbp.exists():
                try:
                    book = json.loads(lbp.read_text("utf-8")).get("last_book", "")
                except Exception:
                    pass

        if not book:
            return Response("Nema aktivne knjige. Odaberi i pokreni obradu.", mimetype="text/plain")

        clean   = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        if not chk_dir.exists():
            return Response("Nema checkpointa. Obrada još nije počela.", mimetype="text/plain")

        chk_files = sorted(chk_dir.glob("*.chk"))
        if not chk_files:
            return Response("Obrada u toku — nema još sačuvanih blokova.", mimetype="text/plain")

        dijelovi = []
        for chk in chk_files:
            try:
                tekst = chk.read_text("utf-8", errors="ignore").strip()
                if tekst:
                    dijelovi.append(tekst)
            except Exception:
                continue

        if not dijelovi:
            return Response("Checkpointi su prazni.", mimetype="text/plain")

        # Spoji sve blokove s dvostrukim prelaskom — čist plain text
        sadrzaj = "\n\n".join(dijelovi)
        return Response(sadrzaj, mimetype="text/plain; charset=utf-8")

    except Exception as e:
        return Response(f"Greška: {e}", mimetype="text/plain")

