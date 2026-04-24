#!/usr/bin/env python3
# run.py – Wrapper za modularni Skriptorij V10.2

import os
import re
import sys
import shutil
import zipfile
import asyncio
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

def start_skriptorij_from_master(bookpathstr, modelname, sharedstats, shared_controls):
    engine = SkriptorijAllInOne(bookpathstr, modelname, sharedstats, shared_controls)
    engine.log("🚀 V10.2 Modularni Omni-Core pokrenut — print-ready + quality scoring aktivan", "system")

    engine.work_dir.mkdir(parents=True, exist_ok=True)
    engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    _no_cisti_chk_fajlove(engine.checkpoint_dir, log_fn=engine.log)

    engine._load_chapter_summaries()

    if engine.book_path.suffix.lower() == ".mobi":
        if not HAS_MOBI:
            engine.log("Greška! MOBI dekoder nije instaliran. Pokrenite: pip install mobi", "error")
            sharedstats["status"] = "ZAUSTAVLJENO"
            return
        engine.log(f"Razbijam MOBI strukturu: {engine.book_path.name}...", "system")
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
            engine.log("MOBI uspješno konvertovan. Nastavljam V10.2 obradu.", "system")
        except Exception as e:
            engine.log(f"MOBI ekstrakcija neuspješna: {e}", "error")
            sharedstats["status"] = "ZAUSTAVLJENO"
            return
    else:
        with zipfile.ZipFile(engine.book_path, "r") as z:
            z.extractall(engine.work_dir)

    engine.html_files = sorted(
        [f for f in engine.work_dir.rglob("*") if f.suffix.lower() in [".html", ".htm", ".xhtml", ".xml"]],
        key=lambda x: x.name,
    )

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
        engine.log(f"🧹 HTML pre-processing: {ocisceno_html} fajl(ov)a očišćeno.", "tech")

    for f in engine.html_files:
        try:
            engine.global_total_chunks += len(engine.chunk_html(f.read_text("utf-8", errors="ignore")))
        except Exception:
            pass

    async def main_loop():
        if engine.html_files and not engine.knjiga_analizirana:
            try:
                intro = engine.html_files[0].read_text("utf-8", errors="ignore")
                await engine.analiziraj_knjigu(intro)
            except Exception as e:
                engine.log(f"Analiza pala: {e}. Nastavljam s defaultima.", "warning")

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

    asyncio.run(main_loop())

    if not shared_controls.get("stop") and not shared_controls.get("reset"):
        engine.shared_stats["status"] = "Završno oblikovanje..."
        for hf in engine.html_files:
            try:
                soup = BeautifulSoup(hf.read_text("utf-8"), "html.parser")
                engine.apply_dropcap_and_toc(soup, hf)
                hf.write_text(str(soup), encoding="utf-8")
            except Exception:
                pass
        engine.generate_ncx()
        engine.finalize()


if __name__ == "__main__":
    import asyncio
    force_mode = "--force" in sys.argv
    only_bad_mode = "--only-bad" in sys.argv

    WORK_DIR = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and Path(arg).exists():
            WORK_DIR = arg
            break

    if WORK_DIR is None:
        print("Usage: python run.py [--force|--only-bad] <work_dir>")
        sys.exit(1)

    shared_stats = {"status": "V10.2 RETRO RE-LEKTURA"}
    shared_controls = {"stop": False, "reset": False, "pause": False}

    engine = SkriptorijAllInOne(
        Path(WORK_DIR).parent / "dummy.epub",
        "dummy",
        shared_stats,
        shared_controls,
    )
    engine.work_dir = Path(WORK_DIR)

    from core.quality import _QUALITY_RESCUE_THRESHOLD
    if force_mode:
        print("🚀 Mod: FORCE — sve blokove prolazi kroz V10.2 pipeline")
    elif only_bad_mode:
        print(f"🎯 Mod: ONLY-BAD — samo blokove s quality score < {_QUALITY_RESCUE_THRESHOLD}")
    else:
        print("🔄 Mod: STANDARDNI V10.2 retro pass")

    asyncio.run(
        engine.retroaktivna_relektura_v10(
            force=force_mode,
            only_bad=only_bad_mode,
        )
    )
