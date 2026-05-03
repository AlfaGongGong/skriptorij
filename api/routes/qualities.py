

# api/routes/quality.py
"""
Rute za quality scores — dohvat i prikaz po blokovima i fajlovima.
"""
import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import CHECKPOINT_BASE_DIR, SHARED_STATS

bp = Blueprint("quality_routes", __name__)


def _get_quality_cache_path() -> Path | None:
    """Pronalazi quality_scores.json za aktivni ili zadnji projekt."""
    import re as _re

    # 1. Aktivni output_file → stem → _skr_{stem}/checkpoints/
    output_file = SHARED_STATS.get("output_file", "")
    if output_file:
        stem = _re.sub(r"[^a-zA-Z0-9_\-]", "", Path(output_file).stem)
        candidate = CHECKPOINT_BASE_DIR / f"_skr_{stem}" / "checkpoints" / "quality_scores.json"
        if candidate.exists():
            return candidate

    # 2. Aktivna knjiga iz SHARED_STATS
    current = SHARED_STATS.get("current_file", "")
    if current:
        stem = _re.sub(r"[^a-zA-Z0-9_\-]", "", Path(current).stem)
        candidate = CHECKPOINT_BASE_DIR / f"_skr_{stem}" / "checkpoints" / "quality_scores.json"
        if candidate.exists():
            return candidate

    # 3. Najnoviji _skr_ direktorij
    if CHECKPOINT_BASE_DIR.exists():
        skr_dirs = sorted(
            CHECKPOINT_BASE_DIR.glob("_skr_*"),
            key=lambda d: d.stat().st_mtime, reverse=True
        )
        for skr in skr_dirs:
            qs = skr / "checkpoints" / "quality_scores.json"
            if qs.exists():
                return qs

    return None


@bp.route("/api/quality_scores")
def get_quality_scores():
    """
    Vraća quality scores za aktivan projekt.
    Response:
    {
      "scores": {"stem": score, ...},
      "summary": {avg, min, max, total, excellent, good, poor, critical, pct_print_ready},
      "by_file": {"filename": {avg, count, blocks: [{stem, score}]}},
      "has_data": bool
    }
    """
    try:
        from core.quality import quality_summary

        cache_path = _get_quality_cache_path()
        if not cache_path:
            return jsonify({
                "scores": {},
                "summary": {},
                "by_file": {},
                "has_data": False,
                "message": "Nema quality scores podataka. Pokreni obradu prvo."
            })

        scores = json.loads(cache_path.read_text("utf-8"))
        if not scores:
            return jsonify({"scores": {}, "summary": {}, "by_file": {}, "has_data": False})

        summary = quality_summary(scores)

        # Grupiši po fajlu
        by_file: dict = {}
        for stem, score in sorted(scores.items()):
            parts = stem.split("_blok_")
            file_name = parts[0] if len(parts) == 2 else stem
            if file_name not in by_file:
                by_file[file_name] = {"blocks": [], "total_score": 0.0, "count": 0}
            by_file[file_name]["blocks"].append({"stem": stem, "score": round(score, 1)})
            by_file[file_name]["total_score"] += score
            by_file[file_name]["count"] += 1

        # Izračunaj avg po fajlu
        for fn in by_file:
            cnt = by_file[fn]["count"]
            by_file[fn]["avg"] = round(by_file[fn]["total_score"] / cnt, 2) if cnt else 0.0
            del by_file[fn]["total_score"]
            # Sortiraj blokove po indeksu
            by_file[fn]["blocks"].sort(key=lambda x: x["stem"])

        return jsonify({
            "scores": scores,
            "summary": summary,
            "by_file": by_file,
            "has_data": True,
            "source": str(cache_path)
        })

    except Exception as e:
        return jsonify({"error": str(e), "has_data": False}), 500


@bp.route("/api/quality_scores/file/<path:file_name>")
def get_quality_for_file(file_name):
    """Vraća quality scores samo za jedan fajl."""
    try:
        from core.quality import quality_summary

        cache_path = _get_quality_cache_path()
        if not cache_path:
            return jsonify({"error": "Nema podataka"}), 404

        scores = json.loads(cache_path.read_text("utf-8"))
        file_scores = {k: v for k, v in scores.items() if k.startswith(file_name)}

        return jsonify({
            "file": file_name,
            "scores": file_scores,
            "summary": quality_summary(file_scores)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/api/quality_scores/send_to_fix", methods=["POST"])
def send_to_fix_route():
    """
    Dohvata listu loših blokova i pokreće send_to_fix na njima.
    POST body (opcionalno): {"threshold": 6.5}
    Delegira na /api/fix/bad_blocks koji pokreće thread.
    """
    from flask import redirect, url_for
    # Delegiraj na processing route koji zna za threading
    try:
        data = request.get_json(silent=True) or {}
        threshold = float(data.get("threshold", 6.5))

        cache_path = _get_quality_cache_path()
        if not cache_path:
            return jsonify({"error": "Nema quality scores podataka"}), 404

        scores = json.loads(cache_path.read_text("utf-8"))
        losi = {k: v for k, v in scores.items() if v < threshold}

        return jsonify({
            "losi_blokovi": len(losi),
            "threshold": threshold,
            "preporuka": (
                "Pokreni /api/fix/bad_blocks POST s istim book i threshold parametrima"
                if losi else "Nema loših blokova"
            ),
            "blokovi": list(losi.keys())[:20],  # Max 20 u preview
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500





# ─── PATCH v4: Dodaj u api/routes/qualities.py (ili processing.py) ────────────

@bp.route("/api/fix/marked_blocks", methods=["POST"])
def fix_marked_blocks():
    """
    FIX 2: Korisnik ručno označava blokove u UI i šalje ih ovdje.
    Backend briše njihove .chk fajlove i pokreće retro samo za njih.

    POST body:
        {"book": "knjiga.epub", "stems": ["chapter002.html_blok_3", ...]}
    """
    try:
        data     = request.get_json(silent=True) or {}
        book     = data.get("book") or SHARED_STATS.get("current_file", "")
        stems    = data.get("stems", [])
        model    = data.get("model", SHARED_STATS.get("active_engine", "V10_TURBO"))

        if not book:
            return jsonify({"error": "Nije odabrana knjiga"}), 400
        if not stems:
            return jsonify({"error": "Nema označenih blokova"}), 400

        import re as _re
        clean   = _re.sub(r"[^a-zA-Z0-9_\-]", "", Path(book).stem)
        chk_dir = Path(PROJECTS_ROOT) / f"_skr_{clean}" / "checkpoints"

        if not chk_dir.exists():
            return jsonify({"error": f"Checkpoint dir nije pronađen: {chk_dir}"}), 404

        # Briši .chk fajlove za označene stemove
        obrisano = 0
        za_retro = []
        for stem in stems:
            chk = chk_dir / f"{stem}.chk"
            if chk.exists():
                try:
                    chk.unlink()
                    obrisano += 1
                    za_retro.append(stem)
                except Exception as e:
                    pass
            # Ukloni iz quality_scores
            SHARED_STATS.get("quality_scores", {}).pop(stem, None)

        if not za_retro:
            return jsonify({"status": "ok", "obrisano": 0,
                            "poruka": "Nijedan .chk fajl nije pronađen — možda već obrisani."})

        # Pokreni retro pipeline u pozadini
        import asyncio, threading

        SHARED_CONTROLS.update({"pause": False, "stop": False, "reset": False})
        SHARED_STATS.update({
            "status": f"RELEKTURA {len(za_retro)} OZNAČENIH BLOKOVA...",
            "current_file": book,
            "active_engine": model,
            "pct": 0,
        })

        def _run():
            try:
                from core.engine import SkriptorijAllInOne
                from processing.retro import retroaktivna_relektura_v10
                full_path = str(Path(INPUT_DIR) / book)
                eng = SkriptorijAllInOne(full_path, model, SHARED_STATS, SHARED_CONTROLS)
                # Učitaj scores
                import json as _j
                qs_path = eng.checkpoint_dir / "quality_scores.json"
                if qs_path.exists():
                    try:
                        SHARED_STATS["quality_scores"] = _j.loads(qs_path.read_text("utf-8"))
                    except Exception:
                        pass
                SHARED_STATS["status"] = f"RELEKTURA {len(za_retro)} BLOKOVA..."
                asyncio.run(retroaktivna_relektura_v10(eng, force=True, only_bad=False))
                SHARED_STATS["status"] = "RELEKTURA ZAVRŠENA"
                SHARED_STATS["pct"] = 100
            except Exception as exc:
                import traceback as _tb
                SHARED_STATS["status"] = f"RELEKTURA GREŠKA: {exc}"
                SHARED_STATS["live_audit"] = (
                    SHARED_STATS.get("live_audit", "") +
                    f"[MARKED REFIX ERROR] {_tb.format_exc()}"
                )

        threading.Thread(target=_run, daemon=True).start()

        return jsonify({
            "status": "Started",
            "book": book,
            "obrisano": obrisano,
            "stemovi": za_retro,
            "poruka": f"Pokrenuta relektura za {obrisano} označenih blokova"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/human_review", methods=["GET", "POST"])
def human_review():
    """
    GET  → vraća JSON status ljudske revizije
    POST → sprema bilješku o reviziji

    FIX: Endpoint mora UVIJEK vraćati application/json
    """
    if request.method == "GET":
        try:
            book = SHARED_STATS.get("current_file", "")
            import re as _re
            clean = _re.sub(r"[^a-zA-Z0-9_\-]", "", Path(book).stem) if book else ""
            review_path = Path(PROJECTS_ROOT) / f"_skr_{clean}" / "checkpoints" / "human_review.json" if clean else None

            if review_path and review_path.exists():
                import json as _j
                items = _j.loads(review_path.read_text("utf-8"))
                return jsonify({
                    "status": "ok",
                    "review": f"Čovjek je označio {len(items)} blokova za reviziju.",
                    "items": items,
                    "count": len(items)
                })
            return jsonify({"status": "ok", "review": "Nema blokova za reviziju.", "items": [], "count": 0})
        except Exception as e:
            return jsonify({"error": str(e), "status": "error"}), 500

    # POST — spremi bilješku
    try:
        data = request.get_json(silent=True) or {}
        stem = data.get("stem", "")
        note = data.get("note", "")
        if not stem:
            return jsonify({"error": "Nedostaje stem"}), 400
        # Spremi bilješku u notes fajl
        book = SHARED_STATS.get("current_file", "")
        import re as _re, json as _j
        clean = _re.sub(r"[^a-zA-Z0-9_\-]", "", Path(book).stem) if book else ""
        if clean:
            notes_path = Path(PROJECTS_ROOT) / f"_skr_{clean}" / "checkpoints" / "review_notes.json"
            notes = {}
            if notes_path.exists():
                try:
                    notes = _j.loads(notes_path.read_text("utf-8"))
                except Exception:
                    pass
            notes[stem] = {"note": note, "ts": __import__("time").time()}
            notes_path.write_text(_j.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"status": "ok", "stem": stem})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── FIX FAZA2: Disk-level ažuriranje quality_scores.json ─────────────────────

def _write_quality_scores(cache_path, scores: dict):
    """Atomično piše quality scores na disk."""
    import json as _j
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(_j.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_path)


@bp.route("/api/quality_scores/<path:stem>", methods=["DELETE"])
def delete_quality_score(stem):
    """
    Briše jedan stem iz quality_scores.json na disku.
    Poziva se nakon što korisnik obriše blok u Review tabu.
    """
    try:
        cache_path = _get_quality_cache_path()
        if not cache_path:
            return jsonify({"status": "ok", "note": "Nema cache-a — ništa za brisati"})

        scores = json.loads(cache_path.read_text("utf-8"))
        existed = stem in scores
        scores.pop(stem, None)

        # Ažuriraj i SHARED_STATS u memoriji
        SHARED_STATS.get("quality_scores", {}).pop(stem, None)

        _write_quality_scores(cache_path, scores)

        return jsonify({
            "status":  "ok",
            "stem":    stem,
            "deleted": existed,
            "remaining": len(scores)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/quality_scores/<path:stem>", methods=["PATCH"])
def patch_quality_score(stem):
    """
    Postavlja score za stem na zadanu vrijednost (default 10.0).
    Poziva se nakon što korisnik ručno sačuva blok u Review tabu.
    Body: {"score": 10.0}  (opcionalno)
    """
    try:
        data  = request.get_json(silent=True) or {}
        score = float(data.get("score", 10.0))

        cache_path = _get_quality_cache_path()
        if not cache_path:
            return jsonify({"status": "ok", "note": "Nema cache-a"})

        scores = json.loads(cache_path.read_text("utf-8"))
        scores[stem] = score

        # Ažuriraj i SHARED_STATS u memoriji
        if "quality_scores" not in SHARED_STATS:
            SHARED_STATS["quality_scores"] = {}
        SHARED_STATS["quality_scores"][stem] = score

        _write_quality_scores(cache_path, scores)

        return jsonify({
            "status": "ok",
            "stem":   stem,
            "score":  score
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

