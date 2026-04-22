#!/usr/bin/env python3
# run.py – Wrapper za modularni Skriptorij V10.2

import asyncio
import sys
from pathlib import Path
from core.engine import SkriptorijAllInOne
from utils.logging import add_audit
from utils.checkpoint_cleaner import _no_cisti_chk_fajlove

def start_skriptorij_from_master(bookpathstr, modelname, sharedstats, shared_controls):
    engine = SkriptorijAllInOne(bookpathstr, modelname, sharedstats, shared_controls)
    engine.log("🚀 V10.2 Modularni Omni-Core pokrenut — optimizovano za free tier", "system")
    engine.work_dir.mkdir(parents=True, exist_ok=True)
    engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    _no_cisti_chk_fajlove(engine.checkpoint_dir, log_fn=engine.log)
    engine._load_chapter_summaries()

    # ... OVDJE KOPIRAJTE OSTATAK ORIGINALNE start_skriptorij_from_master FUNKCIJE ...
    # (raspakivanje EPUB/MOBI, pokretanje main_loop, itd.)
    # Zbog dužine, preuzmite iz starog skriptorij.py

if __name__ == "__main__":
    # CLI entry za retro mod (isto kao original)
    pass
