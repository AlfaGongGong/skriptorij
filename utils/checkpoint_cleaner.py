"""Čišćenje checkpoint fajlova od JSON omotača i placeholder teksta."""
import json
import logging
import re
import shutil
from pathlib import Path

try:
    from core.text_utils import _je_ai_anotacija as _detect_anotacija
except ImportError:
    logging.warning("checkpoint_cleaner: core.text_utils nedostupan — detekcija anotacija isključena")
    _detect_anotacija = None

_PLACEHOLDERS = {
    "lektorisani tekst ovdje", "korigirani tekst ovdje",
    "lektorirani tekst ovdje", "prevedeni tekst ovdje",
    "molim te, pošalji tekst za obradu. čekam ga.",
    "pošalji tekst za obradu.",
    "čekam ga.",
    "[prijevod ovdje]", "[lektura ovdje]", "[tekst ovdje]",
    "ovdje unesite tekst", "tekst za lekturu", "tekst za prijevod",
}

_PHANTOM_CONTAINS = [
    "molim te, pošalji tekst",
    "pošalji tekst za obradu",
    "naravno, evo lektoriranog",
    "naravno, evo prijevoda",
    "evo lektoriranog teksta:",
    "evo prijevoda:",
    "evo korigiranog teksta:",
    "svakako, evo",
    "kao što ste tražili",
    "kao što si tražio",
]


def _ocisti_json_wrapper(sadrzaj: str) -> str:
    stripped = sadrzaj.strip()
    if not stripped.startswith("{"):
        return sadrzaj

    # Normalizuj tipografske navodnike → ASCII za potrebe json.loads.
    # AI modeli ponekad koriste „..." umjesto ASCII "" čak i u JSON omotaču.
    _TYPO_Q = re.compile(r'[\u201e\u201c\u201d\u2018\u2019\u201a\u201b]')

    for candidate in (stripped, _TYPO_Q.sub('"', stripped)):
        try:
            data = json.loads(candidate)
            for k in ("finalno_polirano", "korektura", "tekst", "prijevod"):
                if k in data and isinstance(data[k], str) and data[k].strip():
                    extracted = data[k].strip()
                    if extracted.lower() not in _PLACEHOLDERS:
                        return extracted
        except (json.JSONDecodeError, ValueError):
            pass

    # Regex fallback — handles truncated or malformed JSON wrappers.
    # Strogi (ispravni JSON escape), pa pohlepni (neescape-dani navodnici unutar vrijednosti).
    for k in ("finalno_polirano", "korektura", "tekst", "prijevod"):
        m = re.search(
            rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)',
            stripped,
            re.DOTALL,
        )
        if m:
            raw_val = m.group(1)
            try:
                # json.loads handles all JSON escape sequences (\n, \t, \\, \", …)
                extracted = json.loads(f'"{raw_val}"')
            except (json.JSONDecodeError, ValueError):
                extracted = raw_val
            extracted = extracted.strip()
            if extracted and extracted.lower() not in _PLACEHOLDERS:
                return extracted
        # Pohlepni fallback (.+) — namjerno hvata vrijednosti s neescape-danim
        # ASCII navodnicima unutar HTML sadržaja. Backtracking je O(n), nije eksponencijalan.
        m2 = re.search(
            rf'"{k}"\s*:\s*"(.+)"\s*\}}?\s*$',
            stripped,
            re.DOTALL,
        )
        if m2:
            extracted = m2.group(1).strip()
            if extracted and extracted.lower() not in _PLACEHOLDERS:
                return extracted
    return sadrzaj


def _je_placeholder(sadrzaj: str) -> bool:
    cist = re.sub(r"<[^>]+>", "", sadrzaj).strip().lower()
    if cist in _PLACEHOLDERS or len(cist) < 5:
        return True
    if len(cist) < 150:
        for fraza in _PHANTOM_CONTAINS:
            if fraza in cist:
                return True
    # Provjeri je li sadržaj AI anotacija umjesto čistog teksta
    if _detect_anotacija is not None and _detect_anotacija(sadrzaj):
        return True
    return False


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
            f"{obrisano} placeholder/anotacija fajlova obrisano.",
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