# utils/checkpoint_cleaner.py
"""Čišćenje checkpoint fajlova od JSON omotača i placeholder teksta."""
import json
import re
from pathlib import Path


_PLACEHOLDERS = {
    "lektorisani tekst ovdje",
    "korigirani tekst ovdje",
    "lektorirani tekst ovdje",
    "prevedeni tekst ovdje",
}


def _ocisti_json_wrapper(sadrzaj: str) -> str:
    """Ako je sadržaj JSON s poznatim ključevima, izvuci čisti tekst."""
    s = sadrzaj.strip()
    if not s.startswith("{"):
        return s
    try:
        data = json.loads(s)
        for k in ("finalno_polirano", "korektura", "tekst", "prijevod"):
            if k in data and isinstance(data[k], str) and data[k].strip():
                extracted = data[k].strip()
                # Odbaci placeholder vrijednosti
                if extracted.lower() not in _PLACEHOLDERS:
                    return extracted
    except (json.JSONDecodeError, ValueError):
        pass
    return s


def _je_placeholder(sadrzaj: str) -> bool:
    """Vraća True ako je cijeli sadržaj placeholder tekst."""
    cist = re.sub(r"<[^>]+>", "", sadrzaj).strip().lower()
    return cist in _PLACEHOLDERS or len(cist) < 5


def _no_cisti_chk_fajlove(checkpoint_dir: Path, log_fn=None) -> int:
    """
    Prolazi kroz sve .chk fajlove i:
    1. Izvlači tekst iz JSON omotača
    2. Briše placeholder fajlove
    3. Vraća broj popravljenih fajlova
    """
    if not checkpoint_dir.exists():
        return 0

    popravljeno = 0
    obrisano = 0

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
            f"🧹 Checkpoint čišćenje: {popravljeno} JSON omotača uklonjen, "
            f"{obrisano} placeholder fajlova obrisano.",
            "tech"
        )

    return popravljeno + obrisano
