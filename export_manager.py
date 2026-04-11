# ============================================================================
# SKRIPTORIJ V8 — export_manager.py
# Export rezultata: EPUB metapodaci, PDF/TXT report, JSON
# ============================================================================

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path


def get_epub_metadata(epub_path: str) -> dict:
    """Izvlači metapodatke iz EPUB fajla (OPF manifest)."""
    meta = {
        "title": Path(epub_path).stem,
        "author": "Nepoznat",
        "language": "hr",
        "publisher": "",
        "description": "",
        "file": Path(epub_path).name,
        "size_kb": 0,
    }
    try:
        size = os.path.getsize(epub_path)
        meta["size_kb"] = round(size / 1024, 1)

        with zipfile.ZipFile(epub_path, "r") as z:
            # Pronađi OPF fajl
            opf_name = None
            if "META-INF/container.xml" in z.namelist():
                container = z.read("META-INF/container.xml").decode("utf-8", errors="ignore")
                import re
                m = re.search(r'full-path="([^"]+\.opf)"', container)
                if m:
                    opf_name = m.group(1)

            if opf_name and opf_name in z.namelist():
                opf = z.read(opf_name).decode("utf-8", errors="ignore")
                import re

                def _tag(tag, text):
                    m = re.search(rf"<(?:dc:)?{tag}[^>]*>(.*?)</(?:dc:)?{tag}>", text, re.DOTALL)
                    return m.group(1).strip() if m else ""

                meta["title"] = _tag("title", opf) or meta["title"]
                meta["author"] = _tag("creator", opf) or meta["author"]
                meta["language"] = _tag("language", opf) or meta["language"]
                meta["publisher"] = _tag("publisher", opf) or meta["publisher"]
                meta["description"] = _tag("description", opf)[:300] or meta["description"]
    except Exception:
        pass
    return meta


def generate_json_report(epub_path: str, stats: dict) -> bytes:
    """Generiše JSON fajl s metapodacima i statistikama prijevoda."""
    meta = get_epub_metadata(epub_path)
    report = {
        "generated_at": datetime.now().isoformat(),
        "skriptorij_version": "V8",
        "epub_metadata": meta,
        "translation_stats": {
            "blocks_translated": stats.get("stvarno_prevedeno", 0),
            "blocks_from_cache": stats.get("spaseno_iz_checkpointa", 0),
            "blocks_skipped": stats.get("skipped", "0"),
            "total_chunks": stats.get("ok", "0 / 0"),
            "active_engine": stats.get("active_engine", "---"),
        },
    }
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def generate_txt_report(epub_path: str, stats: dict) -> bytes:
    """Generiše tekstualni izvještaj sa statistikama."""
    meta = get_epub_metadata(epub_path)
    lines = [
        "=" * 60,
        "  SKRIPTORIJ V8 — IZVJEŠTAJ O PRIJEVODU",
        "=" * 60,
        f"  Datum:        {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"  Knjiga:       {meta['title']}",
        f"  Autor:        {meta['author']}",
        f"  Jezik:        {meta['language']}",
        f"  EPUB fajl:    {meta['file']}",
        f"  Veličina:     {meta['size_kb']} KB",
        "-" * 60,
        "  STATISTIKE PRIJEVODA",
        "-" * 60,
        f"  Prevedeno blokova:   {stats.get('stvarno_prevedeno', 0)}",
        f"  Iz cache-a:          {stats.get('spaseno_iz_checkpointa', 0)}",
        f"  Preskočeno:          {stats.get('skipped', '0')}",
        f"  Ukupno obrađeno:     {stats.get('ok', '0 / 0')}",
        f"  Aktivni motor:       {stats.get('active_engine', '---')}",
        "=" * 60,
    ]
    return "\n".join(lines).encode("utf-8")
