"""Čišćenje checkpoint fajlova od JSON omotača i placeholder teksta."""
import json
import re
import shutil
from pathlib import Path

_PLACEHOLDERS = {
    "lektorisani tekst ovdje", "korigirani tekst ovdje",
    "lektorirani tekst ovdje", "prevedeni tekst ovdje",
}


def _ocisti_json_wrapper(sadrzaj: str) -> str:
    if not sadrzaj.strip().startswith("{"):
        return sadrzaj
    try:
        data = json.loads(sadrzaj)
        for k in ("finalno_polirano", "korektura", "tekst", "prijevod"):
            if k in data and isinstance(data[k], str) and data[k].strip():
                extracted = data[k].strip()
                if extracted.lower() not in _PLACEHOLDERS:
                    return extracted
    except (json.JSONDecodeError, ValueError):
        pass
    return sadrzaj


def _je_placeholder(sadrzaj: str) -> bool:
    cist = re.sub(r"<[^>]+>", "", sadrzaj).strip().lower()
    return cist in _PLACEHOLDERS or len(cist) < 5


def _no_cisti_chk_fajlove(checkpoint_dir: Path, log_fn=None) -> int:
    if not checkpoint_dir.exists():
        return 0
    popravljeno = obrisano = 0
    for chk in checkpoint_dir.glob("*.chk"):
        try:
            sadrzaj = chk.read_text("utf-8", errors="ignore")
            if not sadrzaj.strip():
                continue
            ocisceno = _ocisti_json_wrapper(sadrzaj)
            if _je_placeholder(ocisceno):
                chk.unlink()
                obrisano += 1
                continue
            if ocisceno != sadrzaj:
                chk.write_text(ocisceno, encoding="utf-8")
                popravljeno += 1
        except Exception as e:
            if log_fn:
                log_fn(f"⚠️ Greška pri čišćenju {chk.name}: {e}", "warning")
    if log_fn and (popravljeno or obrisano):
        log_fn(
            f"🧹 Checkpoint čišćenje: {popravljeno} JSON omotača uklonjeno, "
            f"{obrisano} placeholder fajlova obrisano.",
            "tech",
        )
    return popravljeno + obrisano


def full_reset(book_stem: str, log_fn=None) -> dict:
    """
    Potpuni reset za jednu knjigu:
      1. Briše cijeli _skr_<book_stem> direktorij unutar CHECKPOINT_BASE_DIR
         (uključuje sve .chk, book_analysis.json, quality_scores.json, ...)
      2. Vraća rječnik s info o tome šta je obrisano.

    Parametri:
        book_stem   — čisti stem naziva knjige (bez ekstenzije i specijalnih znakova),
                      npr. "MojaKnjiga" ili "My_Book_Title"
        log_fn      — opcionalna log funkcija, prima (poruka, tip) poziv

    Vraća:
        {
            "ok": bool,
            "obrisano_dir": str | None,   # putanja obrisanog direktorija
            "greska": str | None,
        }
    """
    from config.settings import CHECKPOINT_BASE_DIR

    # Normaliziraj book_stem — isti regex kao u engine.py
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "", book_stem)
    work_dir = CHECKPOINT_BASE_DIR / f"_skr_{clean_stem}"

    if not work_dir.exists():
        # Pokušaj fuzzy pretragu (prvih 10 znakova) za slučaj neznatnih razlika
        candidates = list(CHECKPOINT_BASE_DIR.glob(f"_skr_{clean_stem[:10]}*"))
        if not candidates:
            msg = f"ℹ️ full_reset: direktorij nije pronađen za '{book_stem}' — nema šta brisati."
            if log_fn:
                log_fn(msg, "info")
            return {"ok": True, "obrisano_dir": None, "greska": None}
        work_dir = candidates[0]

    try:
        shutil.rmtree(work_dir)
        msg = f"🗑️ full_reset: obrisan '{work_dir}'"
        if log_fn:
            log_fn(msg, "system")
        return {"ok": True, "obrisano_dir": str(work_dir), "greska": None}
    except Exception as e:
        msg = f"⚠️ full_reset greška pri brisanju '{work_dir}': {e}"
        if log_fn:
            log_fn(msg, "warning")
        return {"ok": False, "obrisano_dir": str(work_dir), "greska": str(e)}