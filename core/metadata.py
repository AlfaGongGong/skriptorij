"""
core/metadata.py — BooklyFi Metadata Standard v1.0

Jedinstveni metapodaci za sve knjige koje prođu kroz BooklyFi.

Obavezni metapodaci:
  - dc:title        — naslov (bez PREVEDENO_ prefiksa)
  - dc:creator      — autor (Ime Prezime)
  - dc:language     — "hr"
  - dc:identifier   — urn:uuid:...
  - dc:date         — godina originala
  - dc:publisher    — originalni izdavač
  - dc:description  — čist tekst
  - meta cover      — obavezan

BooklyFi metapodaci:
  - booklyfi:version          — 1.0
  - booklyfi:original-file    — originalno ime
  - booklyfi:translated-at    — ISO 8601
  - booklyfi:stylized-at      — ISO 8601
  - booklyfi:source-hash      — SHA256
  - booklyfi:glossary-id      — ID glosara
  - booklyfi:quality-score    — prosječna QA ocjena
  - booklyfi:pipeline-version — V10_TURBO

Verzija: 1.0
"""
from __future__ import annotations

import hashlib
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

BOOKLYFI_VERSION = "1.0"
BOOKLYFI_LANG = "hr"


# ═══════════════════════════════════════════════════════════
# POMOĆNE
# ═══════════════════════════════════════════════════════════

def _clean_text(t: str) -> str:
    """Uklanja HTML tagove iz teksta."""
    if not t:
        return ""
    try:
        return BeautifulSoup(t, "html.parser").get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", "", t).strip()


def _hash_fajla(path: str) -> str:
    """SHA256 hash fajla."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _clean_title(title: str) -> str:
    """Uklanja PREVEDENO_ / _STYLED prefikse/sufikse iz naslova."""
    if not title:
        return ""
    t = title
    t = re.sub(r"^PREVEDENO_", "", t, flags=re.IGNORECASE)
    t = re.sub(r"_STYLED\.epub$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"_STYLED$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\.epub$", "", t, flags=re.IGNORECASE)
    return t.strip()


# ═══════════════════════════════════════════════════════════
# GLAVNA FUNKCIJA
# ═══════════════════════════════════════════════════════════

def standardizuj_metapodatke(
    files: dict,
    opf_path: str,
    epub_path: Optional[str] = None,
    translated_at: Optional[str] = None,
    stylized_at: Optional[str] = None,
    glossary_id: Optional[str] = None,
    quality_score: Optional[float] = None,
    pipeline_version: Optional[str] = None,
) -> dict:
    """
    Standardizuje metapodatke u OPF fajlu.

    :param files:            dict {name: bytes} — svi fajlovi iz EPUB-a
    :param opf_path:         putanja do OPF fajla unutar EPUB-a
    :param epub_path:        putanja do EPUB-a (za hash originala)
    :param translated_at:    ISO 8601 datum prevođenja
    :param stylized_at:      ISO 8601 datum stilizacije
    :param glossary_id:      ID glosara
    :param quality_score:    prosječna QA ocjena
    :param pipeline_version: verzija pipeline-a
    :returns:                dict sa statistikom promjena
    """
    if opf_path not in files:
        return {"ok": False, "greska": f"OPF nije u files: {opf_path}"}

    stats = {
        "title_set": False,
        "creator_set": False,
        "language_set": False,
        "identifier_set": False,
        "date_set": False,
        "publisher_set": False,
        "description_set": False,
        "subject_set": False,
        "booklyfi_meta_added": 0,
    }

    opf_str = files[opf_path].decode("utf-8", errors="replace")
    soup = BeautifulSoup(opf_str, "xml")

    metadata = soup.find("metadata")
    if not metadata:
        return {"ok": False, "greska": "OPF nema <metadata>"}

    # ─── 1. dc:title — čist naslov ────────────────────────
    title_tag = metadata.find("dc:title")
    if title_tag:
        old_title = title_tag.get_text(strip=True)
        new_title = _clean_title(old_title)
        if new_title != old_title:
            title_tag.string = new_title
            stats["title_set"] = True
    else:
        # Ako nema title, uzmi iz imena fajla
        if epub_path:
            new_title = _clean_title(Path(epub_path).name)
            if new_title:
                new_tag = soup.new_tag("dc:title")
                new_tag.string = new_title
                metadata.append(new_tag)
                stats["title_set"] = True

    # ─── 2. dc:creator — obavezno ─────────────────────────
    creator_tag = metadata.find("dc:creator")
    if not creator_tag:
        # Dodaj placeholder
        new_tag = soup.new_tag("dc:creator")
        new_tag.string = "Nepoznat autor"
        metadata.append(new_tag)
        stats["creator_set"] = True

    # ─── 3. dc:language — obavezno "hr" ───────────────────
    lang_tags = metadata.find_all("dc:language")
    for lt in lang_tags:
        lt.decompose()
    new_lang = soup.new_tag("dc:language")
    new_lang.string = BOOKLYFI_LANG
    metadata.append(new_lang)
    stats["language_set"] = True

    # ─── 4. dc:identifier — čist UUID ────────────────────
    id_tags = metadata.find_all("dc:identifier")
    # Zadrži samo prvi, obriši ostale
    if id_tags:
        # Provjeri da li je prvi urn:uuid
        prvi = id_tags[0]
        prvi_text = prvi.get_text(strip=True)
        if not prvi_text.startswith("urn:uuid:"):
            new_uuid = f"urn:uuid:{uuid.uuid4()}"
            prvi.string = new_uuid
            prvi["id"] = "booklyfi-uid"
            stats["identifier_set"] = True
        # Obriši ostale
        for id_tag in id_tags[1:]:
            id_tag.decompose()
    else:
        new_tag = soup.new_tag("dc:identifier", id="booklyfi-uid")
        new_tag.string = f"urn:uuid:{uuid.uuid4()}"
        metadata.append(new_tag)
        stats["identifier_set"] = True

    # ─── 5. dc:date — godina originala ────────────────────
    date_tag = metadata.find("dc:date")
    if date_tag:
        old_date = date_tag.get_text(strip=True)
        # Očisti "0101-01-01T00:00:00+00:00" i slično
        if old_date.startswith("0101") or old_date.startswith("0000"):
            date_tag.decompose()
            stats["date_set"] = True
        else:
            # Skrati na YYYY ili YYYY-MM-DD
            m = re.match(r"(\d{4})(-(\d{2})(-(\d{2}))?)?", old_date)
            if m:
                kratko = m.group(0)
                if kratko != old_date:
                    date_tag.string = kratko
                    stats["date_set"] = True

    # ─── 6. dc:publisher — obavezno ───────────────────────
    pub_tag = metadata.find("dc:publisher")
    if not pub_tag:
        new_tag = soup.new_tag("dc:publisher")
        new_tag.string = "BooklyFi"
        metadata.append(new_tag)
        stats["publisher_set"] = True

    # ─── 7. dc:description — čist tekst ───────────────────
    desc_tag = metadata.find("dc:description")
    if desc_tag:
        old_desc = desc_tag.get_text()
        cist = _clean_text(old_desc)
        if cist != old_desc:
            desc_tag.string = cist
            stats["description_set"] = True

    # ─── 8. dc:subject — žanr ─────────────────────────────
    if not metadata.find("dc:subject"):
        new_tag = soup.new_tag("dc:subject")
        new_tag.string = "Fantasy"
        metadata.append(new_tag)
        stats["subject_set"] = True

    # ─── 9. BooklyFi meta tagovi ──────────────────────────
    # Obriši postojeće booklyfi meta
    for meta in metadata.find_all("meta"):
        name = meta.get("name", "")
        if name.startswith("booklyfi:"):
            meta.decompose()

    booklyfi_meta = {
        "booklyfi:version": BOOKLYFI_VERSION,
        "booklyfi:pipeline-version": pipeline_version or "V10_TURBO",
    }

    if epub_path:
        booklyfi_meta["booklyfi:original-file"] = Path(epub_path).name
        h = _hash_fajla(epub_path)
        if h:
            booklyfi_meta["booklyfi:source-hash"] = h

    if translated_at:
        booklyfi_meta["booklyfi:translated-at"] = translated_at
    if stylized_at:
        booklyfi_meta["booklyfi:stylized-at"] = stylized_at
    if glossary_id:
        booklyfi_meta["booklyfi:glossary-id"] = glossary_id
    if quality_score is not None:
        booklyfi_meta["booklyfi:quality-score"] = f"{quality_score:.2f}"

    for name, content in booklyfi_meta.items():
        new_meta = soup.new_tag("meta")
        new_meta["name"] = name
        new_meta["content"] = content
        metadata.append(new_meta)
        stats["booklyfi_meta_added"] += 1

    # ─── Sačuvaj ──────────────────────────────────────────
    files[opf_path] = str(soup).encode("utf-8")
    stats["ok"] = True
    return stats


def provjeri_metapodatke(files: dict, opf_path: str) -> dict:
    """Provjeri metapodatke u OPF-u (bez mijenjanja)."""
    if opf_path not in files:
        return {"ok": False}

    soup = BeautifulSoup(files[opf_path].decode("utf-8", errors="replace"), "xml")
    metadata = soup.find("metadata")
    if not metadata:
        return {"ok": False}

    rezultat = {"ok": True, "polja": {}}
    for tag in ["dc:title", "dc:creator", "dc:language", "dc:identifier",
                "dc:date", "dc:publisher", "dc:description", "dc:subject"]:
        el = metadata.find(tag)
        rezultat["polja"][tag] = el.get_text(strip=True) if el else None

    # BooklyFi meta
    bf_meta = {}
    for meta in metadata.find_all("meta"):
        name = meta.get("name", "")
        if name.startswith("booklyfi:"):
            bf_meta[name] = meta.get("content", "")
    rezultat["booklyfi"] = bf_meta
    rezultat["ima_cover"] = bool(metadata.find("meta", attrs={"name": "cover"}))

    return rezultat
