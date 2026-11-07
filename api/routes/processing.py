"""
Rute za upravljanje obradom knjiga (files, start, status, modeli).
Dio Skriptorij V12.0 sistema.
"""

import logging
logger = logging.getLogger(__name__)
import contextlib
import json
import logging
import os
import pathlib
import re
import threading
import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import (
    CHECKPOINT_BASE_DIR,
    CONFIG_PATH,
    INPUT_DIR,
    PROJECTS_ROOT,
    SHARED_CONTROLS,
    SHARED_STATS,
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
    # FIX: pošalji ime knjige (origin. .epub, ne HTML)
    try:
        _book = SHARED_STATS.get("current_file", "")
        # Ako je HTML, izvuci iz live_audit
        if not _book or _book.endswith(".html"):
            import re as _re

            _la = SHARED_STATS.get("live_audit", "")
            # Pattern: "Engine inicijaliziran: NAZIV.epub"
            _m = _re.search(
                r"Engine inicijaliziran:&#92;s*([^&#92;s&lt;]+&#92;.epub)", _la
            )
            if not _m:
                _m = _re.search(r"Engine inicijaliziran:\s*([^\s<]+\.epub)", _la)
            if not _m:
                _m = _re.search(
                    r"checkpoint:\s*[^\s]*?/_skr_([^\s/]+)/checkpoints", _la
                )
            if _m:
                _name = _m.group(1)
                _name = _re.sub(r"_[a-f0-9]{20,}", "", _name, flags=_re.IGNORECASE)
                _name = _re.sub(r"--.*$", "", _name)
                _name = _name.replace("_", " ").strip()
                if _name:
                    SHARED_STATS["book_name"] = _name
        else:
            SHARED_STATS["book_name"] = _book
    except Exception:
        logger.exception("[C1_http] processing.py:158 Exception")
    # FIX: ako current_file je prazan, izvuci iz live_audit
    if not SHARED_STATS.get("current_file"):
        try:
            import re as _re

            _la = SHARED_STATS.get("live_audit", "")
            # Pattern: "Engine inicijaliziran: NAZIV.epub"
            _m = _re.search(r"Engine inicijaliziran:\s*([^\s<]+\.epub)", _la)
            if not _m:
                # Pattern: "checkpoint: .../_skr_NAZIV/checkpoints"
                _m = _re.search(
                    r"checkpoint:\s*[^\s]*?/_(?:skr_)([^\s/]+)/checkpoints", _la
                )
            if _m:
                _name = _m.group(1)
                # Ukloni hashove i sufiksе
                _name = _re.sub(r"_[a-f0-9]{20,}", "", _name, flags=_re.IGNORECASE)
                _name = _re.sub(r"--.*$", "", _name)
                _name = _name.replace("_", " ").strip()
                if _name:
                    SHARED_STATS["current_file"] = _name
        except Exception:
            logger.exception("[C1_http] processing.py:181 Exception")
    # FIX: izvuci fazu iz live_audit ako status nije jasan
    if SHARED_STATS.get("status") in ("ANALIZA KNJIGE...", "POKRETANJE...", None):
        try:
            _la = SHARED_STATS.get("live_audit", "")
            if "Retro re-lektura" in _la:
                _m = _re.search(r"Retro re-lektura:\s*(\d+)/(\d+)", _la)
                if _m:
                    SHARED_STATS["retro_info"] = f"{_m.group(1)}/{_m.group(2)} blokova"
        except Exception:
            logger.exception("[C1_http] processing.py:191 Exception")
    return jsonify(SHARED_STATS)


@bp.route("/api/preflight_info", methods=["GET"])
def preflight_info():
    """U1 — procena pre pokretanja: broj fajlova, blokova, aktivnih ključeva."""
    book = request.args.get("book", "")
    full_path = os.path.join(str(INPUT_DIR), book)
    if not book or not os.path.exists(full_path):
        return jsonify({"error": "Knjiga nije pronađena"}), 404

    files = 0
    blocks = 0
    try:
        import zipfile as _zf
        from bs4 import BeautifulSoup as _BS
        from core.chunking import chunk_html as _ch
        with _zf.ZipFile(full_path) as z:
            for n in z.namelist():
                if not n.endswith((".html", ".xhtml")):
                    continue
                if "booklyfi_00" in n or "/nav" in n or "toc" in n.lower():
                    continue
                files += 1
                try:
                    html = z.read(n).decode("utf-8", "replace")
                    soup = _BS(html, "html.parser")
                    text = str(soup.body) if soup.body else str(soup)
                    blocks += len(_ch(text, max_words=500))
                except Exception:
                    blocks += 1
    except Exception as e:
        logger.warning(f"preflight_info: {e}")

    active_keys = 0
    try:
        from api.routes.processing import _fleet
        fl = _fleet()
        if fl:
            active_keys = fl.get_total_active_keys()
    except Exception:
        try:
            from api_fleet import FleetManager
            from config.settings import CONFIG_PATH
            fl = FleetManager(config_path=CONFIG_PATH)
            active_keys = fl.get_total_active_keys() if hasattr(fl, "get_total_active_keys") else 0
        except Exception:
            pass

    return jsonify({
        "book": book,
        "files": files,
        "blocks": blocks,
        "active_keys": active_keys,
    })


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

        book = data["book"]
        model = data.get("model", "V10_TURBO")

        # Podržavamo tool (novi JS) i mode (stari JS) — ali samo RETRO i TTS
        # se prosljeđuju dalje; sve ostalo ide kroz auto-detekciju
        tool = data.get("tool", data.get("mode", "skriptorij")).upper()

        full_path = os.path.join(str(INPUT_DIR), book)
        if not os.path.exists(full_path):
            return jsonify(
                {"error": f"Fajl '{book}' ne postoji na lokaciji: {INPUT_DIR}"}
            ), 404

        # Signaliziraj zaustavljanje eventualnog tekućeg threada
        SHARED_CONTROLS["stop"] = True
        SHARED_CONTROLS["pause"] = False
        SHARED_CONTROLS["reset"] = False

        # Provjeri da li postoje checkpointi (nova putanja)
        chk_count, _ = _get_checkpoint_count_base(Path(full_path))
        has_checkpoints = chk_count > 0

        audit_entry = (
            f"💾 Nastavljam od checkpointa ({chk_count} blokova)...\n"
            if has_checkpoints
            else f"Sistem: Inicijalizacija auto-mode detekcije za: {book}\n"
        )
        SHARED_STATS.update(
            {
                "status": "POKRETANJE...",
                "current_file": book,
                "active_engine": model,
                "pct": SHARED_STATS.get("pct", 0) if has_checkpoints else 0,
                "ok": SHARED_STATS.get("ok", "0 / 0") if has_checkpoints else "0 / 0",
                "live_audit": SHARED_STATS.get("live_audit", "") + audit_entry,
                "output_file": SHARED_STATS.get("output_file")
                if has_checkpoints
                else "",
                "quality_scores": SHARED_STATS.get("quality_scores", {})
                if has_checkpoints
                else {},
                "glosar_problemi": {},
                "knjiga_mode": None,  # engine postavlja
                "knjiga_mode_info": "",
            }
        )

        _start_time = time.time()
        _start_pct = 0

        try:
            with open(os.path.join(PROJECTS_ROOT, "last_book.json"), "w") as f:
                json.dump({"last_book": book}, f)
        except Exception:
            logger.debug("[C3_fallback] processing.py:262 Exception")

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
                    asyncio.run(
                        retroaktivna_relektura_v10(
                            engine,
                            force=False,
                            only_bad=True,
                            bad_threshold=6.5,
                        )
                    )
                    SHARED_STATS["status"] = "ZAVRŠENO (RETRO)"
                    SHARED_STATS["pct"] = 100
                except Exception as exc:
                    import traceback as _tb

                    SHARED_STATS["status"] = f"RETRO GREŠKA: {exc}"
                    SHARED_STATS["live_audit"] = (
                        SHARED_STATS.get("live_audit", "")
                        + f"\n[RETRO ERROR] {_tb.format_exc()}"
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
        # Za RETRO i standardni pipeline: resetuj stop=False da nova obrada može početi.
        # Za TTS: stop ostaje True — TTS ne koristi stop flag, a stari thread se zaustavlja.
        if tool != "TTS":
            SHARED_CONTROLS["stop"] = False
        return jsonify(
            {
                "status": "Started",
                "file": book,
                "tool": tool,
                "mode": "AUTO",  # engine automatski detektuje
                "has_checkpoints": has_checkpoints,
            }
        )

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
    SHARED_CONTROLS["stop"] = True

    reset_result = {}
    if book:
        reset_result = _obrisi_checkpoint_i_kes(book)

    SHARED_STATS.update(
        {
            "pct": 0,
            "ok": "0 / 0",
            "status": "IDLE",
            "live_audit": "Sistem resetovan.\n",
            "quality_scores": {},
            "glosar_problemi": {},
            "knjiga_mode": None,
            "knjiga_mode_info": "",
        }
    )
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

    SHARED_CONTROLS["stop"] = True
    SHARED_CONTROLS["pause"] = False
    SHARED_CONTROLS["reset"] = True

    reset_result = _obrisi_checkpoint_i_kes(book)

    SHARED_STATS.update(
        {
            "status": "IDLE",
            "pct": 0,
            "ok": "0 / 0",
            "skipped": 0,
            "current_file": "",
            "active_engine": "---",
            "live_audit": "Sistem u potpunosti resetovan.\n",
            "output_file": "",
            "quality_scores": {},
            "glosar_problemi": {},
            "knjiga_mode": None,
            "knjiga_mode_info": "",
        }
    )
    return jsonify(
        {
            "ok": reset_result.get("ok", False),
            "book": book,
            "reset": reset_result,
        }
    )


@bp.route("/api/debug/retro_check")
def debug_retro_check():
    """Privremeni endpoint — provjera da li je novi processing.py učitan."""
    import inspect
    import os

    src = inspect.getfile(debug_retro_check)
    mtime = os.path.getmtime(src)
    import datetime

    return jsonify(
        {
            "file": src,
            "modified": datetime.datetime.fromtimestamp(mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "retro_supported": True,
            "auto_mode_support": True,
            "checkpoint_base": str(CHECKPOINT_BASE_DIR),
            "version": "v3_auto_mode",
        }
    )


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
        return jsonify(
            {
                "status": "ok",
                "obrisano": obrisano,
                "poruka": f"Obrisan kompletan cache: {obrisano} blokova",
            }
        )
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
        return jsonify(
            {
                "status": "ok",
                "obrisano": obrisano,
                "threshold": threshold,
                "poruka": f"Obrisano {obrisano} loših blokova (score < {threshold})",
            }
        )
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
    Pronalazi .chk fajl za dati stem, bez obzira na ekstenziju u imenu.
    Stem primjeri: "King_c43_r1.htm_blok_0" ili "King_c43_r1_blok_0"
    Vraća Path objekt (može ne postojati) ili None ako ne može ni pronaći kandidata.
    """
    from pathlib import Path

    chk_dir = Path(chk_dir)

    # 1. Direktno poklapanje (F0.28: prihvati i .prevod.chk i .lektura.chk)
    for ext in (".chk", ".prevod.chk", ".lektura.chk"):
        direct = chk_dir / f"{stem}{ext}"
        if direct.exists():
            return direct

    # 2. Ukloni .htm/.html/.xhtml ispred _blok_ i pokušaj ponovo
    clean_stem2 = re.sub(r"\.(x?html?)(_blok_)", r"\2", stem, flags=re.IGNORECASE)
    clean_stem3 = stem.replace(".htm_", "_").replace(".html_", "_")
    clean_stem1 = re.sub(
        r"\.(x?html?)(_.+)?$", r"\2", stem, flags=re.IGNORECASE
    ).lstrip("_")

    for s in (clean_stem2, clean_stem3, clean_stem1):
        if s == stem:
            continue
        for ext in (".chk", ".prevod.chk", ".lektura.chk"):
            p = chk_dir / f"{s}{ext}"
            if p.exists():
                return p

    # 3. Glob fallback — traži po broju bloka
    blok_match = re.search(r"_blok_(\d+)$", stem)
    if blok_match:
        blok_num = blok_match.group(1)
        base_part = stem.split("_blok_")[0]
        base_clean = re.sub(r"\.(x?html?)$", "", base_part, flags=re.IGNORECASE)
        for pattern in (
            f"*{base_clean}*_blok_{blok_num}.chk",
            f"*_blok_{blok_num}.chk",
        ):
            matches = list(chk_dir.glob(pattern))
            if matches:
                return matches[0]

    # 4. Vrati nepostojeći path (pozivač provjerava .exists())
    return chk_dir / f"{stem}.chk"


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
                with contextlib.suppress(Exception):
                    book = json.loads(last_book_path.read_text("utf-8")).get(
                        "last_book", ""
                    )

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
                logger.exception("[C1_http] processing.py:618 Exception")

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
                        blok_num = parts[1] if len(parts) == 2 else "?"

                        # Kreiraj review item za prikaz u UI
                        reason = _build_reason(score_f)
                        review_items.append(
                            {
                                "stem": stem,
                                "file": file_name,
                                "blok": blok_num,
                                "score": round(score_f, 1),
                                "reason": reason,
                                "source": "quality_scores",
                                "preview": "—",
                            }
                        )
                        seen_stems.add(stem)
            except Exception:
                logger.warning("[C2_parse] processing.py:653 Exception")

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
    # FIX A1: spreci path traversal kroz <path:stem>
    if "/" in chunk_stem or "\\" in chunk_stem or ".." in chunk_stem:
        return jsonify({"error": "invalid stem"}), 400

    try:
        book = SHARED_STATS.get("current_file", "")
        if not book:
            last_book_path = Path(PROJECTS_ROOT) / "last_book.json"
            if last_book_path.exists():
                with contextlib.suppress(Exception):
                    book = json.loads(last_book_path.read_text("utf-8")).get(
                        "last_book", ""
                    )

        if not book:
            # FIX: jsonify umjesto abort(404) — abort vraća HTML stranicu
            return jsonify(
                {"error": "Nema aktivne knjige. Odaberi knjigu pa pokušaj ponovo."}
            ), 404

        # F0.29: skini PREVEDENO_ i _PREVEDENO da bi se nasao pravi _skr_ folder (kao u engine.py)
        _book_stem = Path(book).stem
        _book_stem = re.sub(r"^(?:PREVEDENO_)+", "", _book_stem, flags=re.IGNORECASE)
        _book_stem = re.sub(r"(?:_PREVEDENO|_STYLED)+$", "", _book_stem, flags=re.IGNORECASE)
        clean = re.sub(r"[^a-zA-Z0-9_-]", "", _book_stem)

        # FIX: koristi CHECKPOINT_BASE_DIR (ispravna putanja)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        # Podržava i .chk ekstenziju i bez nje
        stem = chunk_stem.replace(".chk", "")
        chk_path = _resolve_chunk_path(chk_dir, stem)

        # F0.23: fallback na .prevod.chk / .lektura.chk kad glavni .chk ne postoji
        if not chk_path.exists():
            for suffix in (".prevod.chk", ".lektura.chk"):
                candidate = chk_dir / f"{stem}{suffix}"
                if candidate.exists():
                    chk_path = candidate
                    break

        # 2026-11-02: ako nije u aktivnoj knjizi, trazi po SVIM _skr_* folderima
        # (review_list moze prikazati blokove druge knjige kad last_book nije azuriran)
        if not chk_path.exists() and CHECKPOINT_BASE_DIR.exists():
            for _other_skr in CHECKPOINT_BASE_DIR.glob("_skr_*"):
                if _other_skr == chk_dir.parent:
                    continue
                _other_ck = _other_skr / "checkpoints"
                if not _other_ck.exists():
                    continue
                _candidate = _resolve_chunk_path(_other_ck, stem)
                if _candidate.exists():
                    chk_path = _candidate
                    break
                for suffix in (".prevod.chk", ".lektura.chk"):
                    _c2 = _other_ck / f"{stem}{suffix}"
                    if _c2.exists():
                        chk_path = _c2
                        break
                if chk_path.exists():
                    break

        if request.method == "GET":
            if not chk_path.exists():
                return jsonify({"error": f"Chunk nije pronađen: {stem}"}), 404
            text = chk_path.read_text("utf-8", errors="ignore")
            return jsonify({"stem": stem, "text": text})

        if request.method == "POST":
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
        SHARED_STATS.update(
            {
                "status": "FIX LOŠIH BLOKOVA...",
                "current_file": book,
                "active_engine": model,
                "pct": 0,
            }
        )

        import asyncio
        import threading

        from processing.retro import send_to_fix

        def _run_fix():
            try:
                from core.engine import SkriptorijAllInOne

                engine = SkriptorijAllInOne(
                    full_path, model, SHARED_STATS, SHARED_CONTROLS
                )
                SHARED_STATS["status"] = "FIX: BRISANJE LOŠEG CACHE-A..."
                asyncio.run(send_to_fix(engine, score_threshold=threshold))
                SHARED_STATS["status"] = "FIX ZAVRŠEN"
                SHARED_STATS["pct"] = 100
            except Exception as exc:
                import traceback as _tb

                SHARED_STATS["status"] = f"FIX GREŠKA: {exc}"
                SHARED_STATS["live_audit"] = (
                    SHARED_STATS.get("live_audit", "")
                    + f"\n[FIX ERROR] {_tb.format_exc()}"
                )

        thread = threading.Thread(target=_run_fix, daemon=True)
        thread.start()

        return jsonify(
            {
                "status": "Started",
                "book": book,
                "threshold": threshold,
                "poruka": f"Pokrenuto automatsko ispravljanje blokova s scoreom < {threshold}",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/admin/rebuild_review", methods=["POST"])
def rebuild_review():
    """Ručno pokreće mark_for_review za prvi checkpoint aktivne knjige."""
    import json as _json
    import os as _os

    from core.engine import SkriptorijAllInOne

    # 1. Odredi aktivnu knjigu iz SHARED_STATS ili last_book.json
    book = SHARED_STATS.get("current_file", "")
    if not book:
        lbp = Path(PROJECTS_ROOT) / "last_book.json"
        if lbp.exists():
            with contextlib.suppress(Exception):
                book = _json.loads(lbp.read_text()).get("last_book", "")
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

        if hasattr(eng, "mark_for_review"):
            eng.mark_for_review(str(prvi))

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
            with contextlib.suppress(Exception):
                book = json.loads(lbp.read_text()).get("last_book", "")
    if book:
        clean = re.sub(r"[^a-zA-Z0-9_\\-]", "", Path(book).stem)
        hr_path = (
            Path(PROJECTS_ROOT) / f"_skr_{clean}" / "checkpoints" / "human_review.json"
        )
    if hr_path and hr_path.exists():
        try:
            data = json.loads(hr_path.read_text("utf-8"))
            SHARED_STATS["current_file"] = data.get("file_path", "")
            SHARED_STATS["segments"] = data.get("segments", [])
        except Exception:
            logger.exception("[C1_http] processing.py:860 Exception")


_init_review_state()


@bp.route("/api/epub_preview")
def epub_preview():
    """
    Vraća PLAIN TEXT iz svih obrađenih .chk fajlova aktivne knjige.
    Nikad ne vraća HTML grešku — uvijek text/plain.
    """
    from flask import Response

    try:
        book = SHARED_STATS.get("current_file", "") or SHARED_STATS.get(
            "output_file", ""
        )
        if not book:
            lbp = Path(PROJECTS_ROOT) / "last_book.json"
            if lbp.exists():
                with contextlib.suppress(Exception):
                    book = json.loads(lbp.read_text("utf-8")).get("last_book", "")

        if not book:
            return Response(
                "Nema aktivne knjige. Odaberi i pokreni obradu.", mimetype="text/plain"
            )

        clean = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        if not chk_dir.exists():
            return Response(
                "Nema checkpointa. Obrada još nije počela.", mimetype="text/plain"
            )

        chk_files = sorted(chk_dir.glob("*.chk"))
        if not chk_files:
            return Response(
                "Obrada u toku — nema još sačuvanih blokova.", mimetype="text/plain"
            )

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


@bp.route("/api/clean_annotations", methods=["POST"])
def clean_annotations():
    """
    Retroaktivno čišćenje za aktivnu knjiga:
      1. .chk fajlovi — uklanja AI anotacije, JSON omotače (uključujući
         tipografske navodnike „"'') i placeholder tekstove.
      2. HTML fajlovi u work_dir — uklanja { „korektura" i slične JSON omotače
         koji su procurili u EPUB HTML tokom AI obrade (tipografski i ASCII navodnici,
         ugniježđeni JSON u sredini tekst-čvora).

    Body (opcionalno): {"book": "ime.epub"}
    Vraća: {"chk_popravljeno": N, "html_popravljeno": M, "status": "ok"}
    """
    data = request.get_json(silent=True) or {}

    book = (
        data.get("book")
        or SHARED_STATS.get("current_file", "")
        or SHARED_STATS.get("output_file", "")
    )

    if not book:
        lbp = Path(PROJECTS_ROOT) / "last_book.json"
        if lbp.exists():
            with contextlib.suppress(Exception):
                book = json.loads(lbp.read_text("utf-8")).get("last_book", "")

    if not book:
        return jsonify({"error": "Nema aktivne knjige"}), 400

    try:
        from epub.parser import _strip_json_artifacts_from_html
        from utils.checkpoint_cleaner import _no_cisti_chk_fajlove

        # Sanitizacija: dozvoli samo alfanumeričke znakove i _- za stem
        clean = re.sub(r"[^a-zA-Z0-9_-]", "", Path(book).stem)
        work_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}"
        chk_dir = work_dir / "checkpoints"

        # Provjeri da putanja ostaje unutar CHECKPOINT_BASE_DIR
        try:
            work_dir.resolve().relative_to(CHECKPOINT_BASE_DIR.resolve())
        except ValueError:
            return jsonify({"error": "Nevažeća putanja knjige"}), 400

        def _log(msg, tip="info"):
            SHARED_STATS["live_audit"] = SHARED_STATS.get("live_audit", "") + f"\n{msg}"

        # 1. Čišćenje .chk fajlova (JSON omotači + anotacije + placeholder)
        chk_popravljeno = 0
        if chk_dir.exists():
            chk_popravljeno = _no_cisti_chk_fajlove(chk_dir, log_fn=_log)
        else:
            _log("ℹ️ Nema checkpointa za ovu knjigu.")

        # 2. Čišćenje HTML fajlova u work_dir (procurili JSON omotači u EPUB HTML)
        html_popravljeno = 0
        if work_dir.exists():
            from core.natural_sort import natural_sort_key

            html_files = sorted(
                (
                    f
                    for f in work_dir.rglob("*")
                    if f.suffix.lower() in {".html", ".htm", ".xhtml"}
                    and not f.name.startswith(".")
                ),
                key=natural_sort_key,
            )
            if html_files:
                html_popravljeno = _strip_json_artifacts_from_html(
                    html_files, log_fn=_log
                )
            else:
                _log("ℹ️ Nema HTML fajlova za čišćenje u work_dir.")

        return jsonify(
            {
                "chk_popravljeno": chk_popravljeno,
                "html_popravljeno": html_popravljeno,
                "status": "ok",
                "book": Path(book).name,
            }
        )
    except Exception:
        logging.exception("clean_annotations: greška pri čišćenju")
        return jsonify({"error": "Greška pri čišćenju anotacija"}), 500


# ─── B3 FIX: epub_text + epub_plain endpointi za Revizija tab ─────────────────


@bp.route("/api/epub_text/<path:book>")
def epub_text(book):
    """
    Vraća sadržaj .chk fajlova za datu knjigu kao JSON lista blokova.
    Koristi se u Revizija tabu za prikaz prevedenog teksta.
    Response: {"blocks": [{"stem": "...", "text": "...", "score": 7.2}, ...]}
    """
    import json as _j
    import re as _re

    from processing.retro import _je_finalni_chk

    try:
        clean = _re.sub(r"[^a-zA-Z0-9_\-]", "", pathlib.Path(book).stem)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        if not chk_dir.exists():
            return jsonify(
                {"error": f"Checkpoint dir nije pronađen: {chk_dir}", "blocks": []}
            ), 404

        # Učitaj quality scores
        qs_path = chk_dir / "quality_scores.json"
        scores = {}
        if qs_path.exists():
            try:
                raw_scores = _j.loads(qs_path.read_text("utf-8"))
                for k, v in raw_scores.items():
                    if isinstance(v, dict) and "score" in v:
                        scores[k] = float(v["score"])
                    elif isinstance(v, (int, float)):
                        scores[k] = float(v)
            except Exception:
                logger.warning("[C2_parse] processing.py:1048 Exception")

        # Učitaj sadržaj finalnih .chk fajlova
        blocks = []
        for chk in sorted(chk_dir.glob("*.chk")):
            if not _je_finalni_chk(chk):
                continue
            try:
                text = chk.read_text("utf-8", errors="ignore")
                score = scores.get(chk.stem, None)
                blocks.append(
                    {
                        "stem": chk.stem,
                        "text": text,
                        "score": round(score, 1) if score is not None else None,
                    }
                )
            except Exception:
                logger.exception("[C1_http] processing.py:1066 Exception")

        return jsonify({"blocks": blocks, "total": len(blocks), "book": book})

    except Exception as e:
        return jsonify({"error": str(e), "blocks": []}), 500


@bp.route("/api/epub_plain/<path:book>")
def epub_plain(book):
    """
    Kao epub_text ali vraća plain text (bez HTML tagova) — za pretragu i diff.
    Response: {"blocks": [{"stem": "...", "text": "...", "score": 7.2}, ...]}
    """
    import json as _j
    import re as _re

    from bs4 import BeautifulSoup

    from config.settings import CHECKPOINT_BASE_DIR
    from processing.retro import _je_finalni_chk

    try:
        clean = _re.sub(r"[^a-zA-Z0-9_\-]", "", pathlib.Path(book).stem)
        chk_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"

        if not chk_dir.exists():
            return jsonify(
                {"error": f"Checkpoint dir nije pronađen: {chk_dir}", "blocks": []}
            ), 404

        qs_path = chk_dir / "quality_scores.json"
        scores = {}
        if qs_path.exists():
            try:
                raw_scores = _j.loads(qs_path.read_text("utf-8"))
                for k, v in raw_scores.items():
                    scores[k] = float(v["score"]) if isinstance(v, dict) else float(v)
            except Exception:
                logger.warning("[C2_parse] processing.py:1105 Exception")

        blocks = []
        for chk in sorted(chk_dir.glob("*.chk")):
            if not _je_finalni_chk(chk):
                continue
            try:
                raw = chk.read_text("utf-8", errors="ignore")
                try:
                    plain = BeautifulSoup(raw, "html.parser").get_text(
                        separator=" ", strip=True
                    )
                except Exception:
                    plain = _re.sub(r"<[^>]+>", " ", raw).strip()
                score = scores.get(chk.stem, None)
                blocks.append(
                    {
                        "stem": chk.stem,
                        "text": plain,
                        "score": round(score, 1) if score is not None else None,
                    }
                )
            except Exception:
                logger.exception("[C1_http] processing.py:1128 Exception")

        return jsonify({"blocks": blocks, "total": len(blocks), "book": book})

    except Exception as e:
        return jsonify({"error": str(e), "blocks": []}), 500

# ── 2026-11-02: names endpoints (UI ih zvao → 404) ──────────────────────────

@bp.route("/api/names/status", methods=["GET"])
def names_status():
    book = request.args.get("book", "")
    if not book:
        return jsonify({"error": "Nema book parametra", "exists": False, "count": 0}), 200
    from pathlib import Path as _NPath
    candidates = [
        _NPath(str(INPUT_DIR)) / f"{book}.replacement",
        _NPath(str(INPUT_DIR)).parent / "STYLED" / f"{book}.replacement",
    ]
    for p in candidates:
        if p.exists():
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                lines = [l for l in txt.splitlines() if l.strip() and not l.lstrip().startswith("#")]
                return jsonify({"book": book, "exists": True, "count": len(lines), "path": str(p)})
            except Exception:
                pass
    return jsonify({"book": book, "exists": False, "count": 0})


@bp.route("/api/names/replacement", methods=["GET"])
def names_replacement():
    book = request.args.get("book", "")
    if not book:
        return jsonify({"error": "Nema book parametra", "text": ""})
    from pathlib import Path as _NPath
    candidates = [
        _NPath(str(INPUT_DIR)) / f"{book}.replacement",
        _NPath(str(INPUT_DIR)).parent / "STYLED" / f"{book}.replacement",
    ]
    for p in candidates:
        if p.exists():
            try:
                return jsonify({"book": book, "text": p.read_text(encoding="utf-8", errors="ignore"), "path": str(p)})
            except Exception:
                pass
    return jsonify({"book": book, "text": ""})


@bp.route("/api/names/apply", methods=["POST"])
def names_apply():
    data = request.get_json() or {}
    book = data.get("book", "")
    text = data.get("text", "")
    if not book:
        return jsonify({"error": "Nema book parametra"}), 400
    from pathlib import Path as _NPath
    p = _NPath(str(INPUT_DIR)) / f"{book}.replacement"
    try:
        p.write_text(text, encoding="utf-8")
        return jsonify({"ok": True, "path": str(p)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ── P2.6 odluke: pamcenje korisnickih odluka s kartica revizije ──────────────
@bp.route("/api/review/odluka", methods=["POST"])
def review_odluka():
    """Zapisuje odluku korisnika (ostavi / prevedi_ponovo / preskoci / ponisti). Uvijek JSON."""
    from flask import request as _rq
    from core import odluke as _od
    d = _rq.get_json(silent=True) or {}
    try:
        zap = _od.zabiljezi(
            str(d.get("knjiga", "")), str(d.get("blok", "")),
            str(d.get("en", "")), str(d.get("hr", "")),
            str(d.get("tip", "?")), str(d.get("odluka", "")), str(d.get("novo", "")),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "kljuc": zap["kljuc"]})


@bp.route("/api/review/odluke/stat", methods=["GET"])
def review_odluke_stat():
    """Stvarna preciznost po vrsti greske iz korisnikovih klikova."""
    from core import odluke as _od
    return jsonify(_od.statistika())


# ── P2.6 kartice: teske greske verifikatora za pregled ───────────────────────
_P26_TIP_NAZIV = {
    "negacija": "Smisao je obrnut (negacija)",
    "broj": "Broj se ne slaže s originalom",
    "izostavljeno": "Nešto je izostavljeno iz originala",
    "dodano": "Dodano je nešto čega nema u originalu",
    "ime": "Ime je krivo prevedeno",
}
_P26_EN_CACHE = {}
_P26_ORIGINALI = Path("/storage/emulated/0/Books/MoonReader/original")


def _p26_knjiga():
    book = SHARED_STATS.get("current_file", "")
    if not book:
        lb = Path(PROJECTS_ROOT) / "last_book.json"
        if lb.exists():
            try:
                book = json.loads(lb.read_text("utf-8")).get("last_book", "")
            except Exception as e:
                print("[P2.6] last_book.json nečitljiv:", repr(e))
    if not book:
        return ""
    st = Path(book).stem
    st = re.sub(r"^(?:PREVEDENO_)+", "", st, flags=re.IGNORECASE)
    st = re.sub(r"(?:_PREVEDENO|_STYLED)+$", "", st, flags=re.IGNORECASE)
    return re.sub(r"[^a-zA-Z0-9_-]", "", st)


def _p26_en_tekstovi(clean):
    """EN tekst izvornog EPUB-a (trazi se po rijecima iz imena knjige); cache po knjizi."""
    import html as _h
    import zipfile
    if clean in _P26_EN_CACHE:
        return _P26_EN_CACHE[clean]
    tok = [t for t in clean.lower().split("_") if t]
    out = {}
    if tok and _P26_ORIGINALI.exists():
        for f in sorted(_P26_ORIGINALI.glob("*.epub")):
            if all(t in f.name.lower() for t in tok):
                try:
                    with zipfile.ZipFile(f) as z:
                        for n in z.namelist():
                            if n.endswith((".html", ".xhtml")) and "/Text/" in n:
                                raw = z.read(n).decode("utf-8", "ignore")
                                t = _h.unescape(re.sub(r"<[^>]+>", " ", raw))
                                out[n.rsplit("/", 1)[1]] = re.sub(r"\s+", " ", t)
                except Exception as e:
                    print("[P2.6] EN čitanje nije uspjelo:", f, repr(e))
                break
    _P26_EN_CACHE[clean] = out
    return out


def _p26_odlomak(tekstovi, blok, frag, n=300):
    frag = re.sub(r"\s+", " ", (frag or "").strip())
    if len(frag) < 6:
        return ""
    prvi = blok.split(".html_blok")[0] + ".html"
    redoslijed = ([prvi] if prvi in tekstovi else []) + [k for k in sorted(tekstovi) if k != prvi]
    for k in redoslijed:
        t = tekstovi[k]
        for f in (frag, frag.replace("\u2019", "'"), frag.replace("'", "\u2019")):
            i = t.find(f)
            if i >= 0:
                return t[max(0, i - n): i + len(f) + n]
    return ""


@bp.route("/api/review/kartice", methods=["GET"])
def review_kartice():
    """Kartice revizije: samo teske greske verifikatora, bez vec odlucenih. Uvijek JSON."""
    from core import odluke as _od
    from core.verifier import OZNAKA_TEZKI_TIPOVI as _TEZ
    try:
        clean = _p26_knjiga()
        if not clean:
            return jsonify({"error": "Nema aktivne knjige."}), 404
        ck = CHECKPOINT_BASE_DIR / f"_skr_{clean}" / "checkpoints"
        qv = ck / "quality_verifier.json"
        if not qv.exists():
            return jsonify({"error": "Nema rezultata verifikatora za ovu knjigu."}), 404
        d = json.loads(qv.read_text("utf-8"))
        en_t = _p26_en_tekstovi(clean)
        kartice = []
        for k, v in sorted(d.items()):
            if v.get("verifier") == "skip":
                continue
            hr_plain = None
            for g in (v.get("greske") or []):
                tip = g.get("tip")
                if tip not in _TEZ:
                    continue
                en = g.get("en_fragment") or ""
                hr = (g.get("hr_fragment") or "").strip()
                if _od.je_odbacen(en, hr) or _od.odlucen(clean, en, hr):
                    continue
                if hr_plain is None:
                    p = ck / (k if k.endswith(".chk") else k + ".chk")
                    raw = p.read_text("utf-8", "ignore") if p.exists() else ""
                    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
                    hr_plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
                kartice.append({
                    "id": len(kartice) + 1, "knjiga": clean, "blok": k, "tip": tip,
                    "tip_naziv": _P26_TIP_NAZIV.get(tip, tip),
                    "en": en, "hr": hr,
                    "en_kontekst": _p26_odlomak(en_t, k, en),
                    "hr_kontekst": _p26_odlomak({"x": hr_plain}, "", hr, 200),
                })
        return jsonify(kartice)
    except Exception as e:
        print("[P2.6] review_kartice greška:", repr(e))
        return jsonify({"error": str(e)}), 500


@bp.route("/revizija", methods=["GET"])
def revizija_stranica():
    from flask import render_template
    return render_template("revizija.html")
