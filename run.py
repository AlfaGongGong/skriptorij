#!/usr/bin/env python3
# run.py — Booklyfi V10.2  PATCH v4
# Auto-detekcija moda: PREVOD | LEKTURA | AUTO-RETRO
# Checkpoint putanja: CHECKPOINT_BASE_DIR/_skr_X (nova centralna lokacija)
#
# FIX: mark_for_review se sada automatski poziva nakon završetka main_loop-a
#      unutar async konteksta — bez nested asyncio.run()

import os, re, sys, shutil, zipfile, asyncio, json
from pathlib import Path
from bs4 import BeautifulSoup

from core.engine import SkriptorijAllInOne
from utils.logging import add_audit
from utils.checkpoint_cleaner import _no_cisti_chk_fajlove
from epub.parser import _ocisti_epub_html, _ukloni_inline_stilove, _zamijeni_epub_css

try:
    import mobi
    HAS_MOBI = True
except ImportError:
    HAS_MOBI = False


def _ucitaj_quality_scores(engine, sharedstats):
    """Učitaj quality_scores.json u shared_stats pri startu sesije."""
    try:
        qs_path = engine.checkpoint_dir / "quality_scores.json"
        if qs_path.exists():
            qs = json.loads(qs_path.read_text("utf-8"))
            if "quality_scores" not in sharedstats:
                sharedstats["quality_scores"] = {}
            sharedstats["quality_scores"].update(qs)
            engine.log(
                f"📊 Učitani quality scores: {len(qs)} blokova iz prethodne sesije",
                "system",
            )
            return qs
    except Exception as e:
        engine.log(f"⚠️ Quality scores učitavanje palo: {e}", "warning")
    return {}


def _odredi_strategiju(engine, html_files, scores: dict) -> str:
    """
    Određuje strategiju obrade na osnovu:
      1. Je li knjiga EN ili HR/BS → PREVOD ili LEKTURA
      2. Koliko loših blokova postoji u cache-u → AUTO-RETRO

    Vraća: "PREVOD" | "LEKTURA" | "AUTO-RETRO"
    """
    from core.quality import _QUALITY_RESCUE_THRESHOLD

    if scores:
        losi = [v for v in scores.values() if v < _QUALITY_RESCUE_THRESHOLD]
        pct_losi = len(losi) / len(scores) if scores else 0

        if pct_losi > 0.30:
            engine.log(
                f"🔁 AUTO-RETRO detekcija: {len(losi)}/{len(scores)} blokova "
                f"lošeg kvaliteta ({pct_losi:.0%}) → pokrecemo retro re-lekturu",
                "system",
            )
            return "AUTO-RETRO"

    # Detektuj jezik knjige — poziva _detect_knjiga_mode() UVIJEK na početku
    knjiga_mode = engine._detect_knjiga_mode(html_files, n_files=5)
    return knjiga_mode  # "PREVOD" ili "LEKTURA"


def _pametni_reset_cachea(engine, scores: dict, sharedstats):
    """
    Reset ne briše SVE — briše SAMO blokove s lošim scoreom.
    Blokovi dobrog kvaliteta ostaju u cache-u.
    """
    from core.quality import _QUALITY_RESCUE_THRESHOLD

    if not scores:
        return 0

    chk_dir = engine.checkpoint_dir
    losi = [
        chk for chk in chk_dir.glob("*.chk")
        if scores.get(chk.stem, 10.0) < _QUALITY_RESCUE_THRESHOLD
    ]

    if not losi:
        engine.log("✅ Svi cache blokovi dobrog kvaliteta — zadržavamo cache.", "system")
        return 0

    for chk in losi:
        try:
            chk.unlink()
        except Exception:
            pass

    for chk in losi:
        sharedstats.get("quality_scores", {}).pop(chk.stem, None)

    engine.log(
        f"🧹 Pametni reset: obrisano {len(losi)} loših blokova "
        f"(dobri ostaju u cache-u)",
        "system",
    )
    return len(losi)


def start_skriptorij_from_master(bookpathstr, modelname, sharedstats, shared_controls):
    """
    Glavna entry točka. Poziva je app.py u zasebnom threadu.
    Mode se NE prima kao parametar — engine ga sam detektuje UVIJEK na početku:
      - Ako postoje checkpointi → nastavlja od mjesta prekida
      - Ako nema checkpointa → počinje od nule
      - Automatski bira: PREVOD | LEKTURA | AUTO-RETRO
    """
    engine = SkriptorijAllInOne(bookpathstr, modelname, sharedstats, shared_controls)
    engine.log("🚀 V10.2 Booklyfi pokrenut — auto-mode detekcija aktiva", "system")
    engine.log(f"📁 Checkpoint putanja: {engine.checkpoint_dir}", "tech")

    engine.work_dir.mkdir(parents=True, exist_ok=True)
    engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    _no_cisti_chk_fajlove(engine.checkpoint_dir, log_fn=engine.log)

    # ── Učitaj quality scores odmah pri startu ─────────────────────────────
    scores = _ucitaj_quality_scores(engine, sharedstats)

    engine._load_chapter_summaries()

    # ── MOBI ekstrakcija ──────────────────────────────────────────────────
    if engine.book_path.suffix.lower() == ".mobi":
        if not HAS_MOBI:
            engine.log("Greška! pip install mobi", "error")
            sharedstats["status"] = "ZAUSTAVLJENO"
            return
        engine.log(f"Razbijam MOBI: {engine.book_path.name}...", "system")
        sharedstats["status"] = "RASPAKOVANJE MOBI-ja..."
        try:
            tempdir, filepath = mobi.extract(str(engine.book_path))
            extracted_path = Path(filepath)
            if extracted_path.suffix.lower() == ".epub":
                with zipfile.ZipFile(extracted_path, "r") as z:
                    z.extractall(engine.work_dir)
            elif extracted_path.is_dir():
                for item in extracted_path.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(extracted_path)
                        target = engine.work_dir / rel_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(item, target)
            else:
                shutil.copy(extracted_path, engine.work_dir / extracted_path.name)
            try:
                shutil.rmtree(tempdir, ignore_errors=True)
            except Exception:
                pass
            engine.log("MOBI konvertovan. Nastavljam.", "system")
        except Exception as e:
            engine.log(f"MOBI ekstrakcija neuspješna: {e}", "error")
            sharedstats["status"] = "ZAUSTAVLJENO"
            return
    else:
        with zipfile.ZipFile(engine.book_path, "r") as z:
            z.extractall(engine.work_dir)

    # ── Pronađi HTML fajlove ──────────────────────────────────────────────
    engine.html_files = sorted(
        [f for f in engine.work_dir.rglob("*")
         if f.suffix.lower() in [".html", ".htm", ".xhtml", ".xml"]],
        key=lambda x: x.name,
    )

    # ── Pre-processing HTML-a ─────────────────────────────────────────────
    _ukloni_inline_stilove(engine.html_files, engine.log)
    _zamijeni_epub_css(engine.html_files, engine.work_dir, engine.log)

    ocisceno_html = 0
    for hf in engine.html_files:
        try:
            original = hf.read_text("utf-8", errors="ignore")
            cleaned = _ocisti_epub_html(original)
            if cleaned != original:
                hf.write_text(cleaned, encoding="utf-8")
                ocisceno_html += 1
        except Exception:
            pass
    if ocisceno_html:
        engine.log(f"🧹 HTML pre-processing: {ocisceno_html} fajlova.", "tech")

    # ── Prebrojavanje chunkova za ETA ─────────────────────────────────────
    for f in engine.html_files:
        try:
            engine.global_total_chunks += len(
                engine.chunk_html(f.read_text("utf-8", errors="ignore"))
            )
        except Exception:
            pass

    # ── Auto-detekcija strategije (_detect_knjiga_mode UVIJEK na početku) ─
    sharedstats["status"] = "ANALIZA KNJIGE..."

    # Provjeri postoje li checkpointi — auto-detekcija nastavlja ili počinje od nule
    chk_count = len(list(engine.checkpoint_dir.glob("*.chk")))
    if chk_count > 0:
        engine.log(
            f"💾 Pronađeno {chk_count} checkpointa — nastavljam od mjesta prekida.",
            "system",
        )

    strategija = _odredi_strategiju(engine, engine.html_files, scores)

    if strategija == "AUTO-RETRO":
        _pametni_reset_cachea(engine, scores, sharedstats)
        # Postavi LEKTURA ili PREVOD ovisno o knjizi
        engine._detect_knjiga_mode(engine.html_files, n_files=5)
        engine.log(
            f"🔁 AUTO-RETRO: loši blokovi obrisani, nastavljam "
            f"normalnim {engine.knjiga_mode} tokom",
            "system",
        )
    else:
        engine.knjiga_mode = strategija

    sharedstats["knjiga_mode"] = engine.knjiga_mode
    engine.log(
        f"📖 Knjiga: <b>{engine.book_path.name}</b> → "
        f"<b>{engine.knjiga_mode}</b>",
        "system",
    )

    # ── Glavna asyncio petlja ─────────────────────────────────────────────
    async def main_loop():
        if engine.html_files and not engine.knjiga_analizirana:
            try:
                intro = engine.html_files[0].read_text("utf-8", errors="ignore")
                await engine.analiziraj_knjigu(intro)
            except Exception as e:
                engine.log(f"Analiza pala: {e}. Nastavljam s defaultima.", "warning")

        sharedstats["status"] = (
            "LEKTURA U TOKU..." if engine.knjiga_mode == "LEKTURA"
            else "PREVOD U TOKU..."
        )

        for i, hf in enumerate(engine.html_files, 1):
            if shared_controls.get("stop") or shared_controls.get("reset"):
                break

            engine.log(f"📄 Poglavlje {i}/{len(engine.html_files)}: {hf.name}", "system")
            await engine.process_single_file_worker(hf)
            engine.buildlive_epub()
            engine._chapters_processed += 1

            if engine._chapters_processed % engine.GLOSAR_UPDATE_INTERVAL == 0:
                try:
                    tekst_pog = hf.read_text("utf-8", errors="ignore")
                    await engine._inkrementalna_analiza_glosara(tekst_pog, hf.name)
                except Exception as e:
                    engine.log(f"⚠️ Glosar update pao: {e}", "warning")

        # ── FIX: automatski poziv mark_for_review nakon završetka obrade ──
        # Prethodno se NIKAD nije pozivao → human_review.json nije postojao
        # → /api/review/list uvijek vraćao prazan [] → tab za reviziju uvijek prazan.
        # Pozivamo unutar async konteksta da izbjegnemo nested asyncio.run().
        if not shared_controls.get("stop") and not shared_controls.get("reset"):
            try:
                sharedstats["status"] = "GENERISANJE REVIZIJE..."
                await engine.mark_for_review()
                engine.log("📋 Lista za reviziju ažurirana.", "system")
            except Exception as e:
                engine.log(f"⚠️ mark_for_review pao: {e}", "warning")

    asyncio.run(main_loop())

    # ── Finalizacija ──────────────────────────────────────────────────────
    if not shared_controls.get("stop") and not shared_controls.get("reset"):
        sharedstats["status"] = "Završno oblikovanje..."
        for hf in engine.html_files:
            try:
                soup = BeautifulSoup(hf.read_text("utf-8"), "html.parser")
                engine.apply_dropcap_and_toc(soup, hf)
                hf.write_text(str(soup), encoding="utf-8")
            except Exception:
                pass
        engine.generate_ncx()

        try:
            qs = engine.shared_stats.get("quality_scores", {})
            if not qs and hasattr(engine, "_quality_scores"):
                for k, v in engine._quality_scores.items():
                    if isinstance(v, (int, float)):
                        qs[k] = float(v)
                    elif isinstance(v, dict) and "score" in v:
                        qs[k] = float(v["score"])
            if qs:
                qs_path = engine.checkpoint_dir / "quality_scores.json"
                qs_path.write_text(
                    json.dumps(qs, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                engine.log(
                    f"💾 Quality scores sačuvani: {len(qs)} blokova", "system"
                )
        except Exception as e:
            engine.log(f"⚠️ Quality scores snimanje palo: {e}", "warning")

        engine.finalize()


if __name__ == "__main__":
    WORK_DIR = next(
        (a for a in sys.argv[1:] if not a.startswith("--") and Path(a).exists()),
        None,
    )
    if WORK_DIR is None:
        print("Usage: python run.py <work_dir>")
        sys.exit(1)

    shared_stats    = {"status": "V10.2 AUTO-MODE"}
    shared_controls = {"stop": False, "reset": False, "pause": False}
    engine = SkriptorijAllInOne(
        Path(WORK_DIR).parent / "dummy.epub", "dummy",
        shared_stats, shared_controls,
    )
    engine.work_dir = Path(WORK_DIR)
    asyncio.run(engine.retroaktivna_relektura_v10(force=False, only_bad=True))