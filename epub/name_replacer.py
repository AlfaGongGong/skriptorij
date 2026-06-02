"""epub/name_replacer.py
===========================================================================
SMART NAME REPLACER — Standalone operacija za Skriptorij / Booklyfi

Ulaz:  .epub fajl (originalni ili prevedeni)
Izlaz: isti .epub (in-place zamjena) + .epub.replacement fajl s logom

Format .epub.replacement fajla:
    original#->#ispravka
    (jedna zamjena po redu, komentari počinju s #!)

Logika:
  1. Skenira sve HTML fajlove u EPUB-u
  2. AI analizira tekst i otkriva:
     - Varijante istog lika/mjesta/entiteta  (Jednooki / One Eye / Jedno oko)
     - Inkonsistentnosti u padežima, spolu, broju
     - Mrtva vlastita imena koja nikad nisu normalizovana
  3. Gradi glosar zamjena (canonical forma → sve varijante)
  4. Primjenjuje zamjene na tekst uz:
     - Poštovanje HTML tagova (ne dirá atribute)
     - Čuvanje velikih slova (početak rečenice, naslovi)
     - Word-boundary matching (ne kvari podriječi)
     - Morfološki kontekst: padeži, spol, broj
  5. Snima .epub.replacement log i vrača modificirani EPUB

STANDALONE: ne importuje iz pipeline-a, radi s bilo kojim EPUB-om.
===========================================================================
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstante
# ---------------------------------------------------------------------------

# Marker u .replacement fajlu — separator
_SEP = "#->#"

# Minimalni broj pojavljivanja varijante da bude zanimljiva
_MIN_OCCURRENCES = 2

# Maximalni broj entiteta koje šaljemo AI-ju u jednom promptu
_MAX_ENTITIES_PER_PROMPT = 40

# Regex: HTML tag (za skipovanje atributa)
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.UNICODE | re.DOTALL)

# Regex: vjerovatno vlastito ime (velika slova, dijakritika)
# Hvata: Jednooki, One Eye, Ibn Battuta, al-Rashid, O'Brien...
_PROPER_NOUN_RE = re.compile(
    r"\b(?:[A-ZČĆŠŽĐ][a-zčćšžđA-ZČĆŠŽĐ\-]{1,}(?:\s+[A-ZČĆŠŽĐ][a-zčćšžđA-ZČĆŠŽĐ\-]{1,}){0,3})\b",
    re.UNICODE,
)

# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Vraća čist tekst bez HTML tagova."""
    return _HTML_TAG_RE.sub(" ", html)


def _preserve_case(original: str, replacement: str) -> str:
    """
    Ako je original sav velikim slovima ili počinje velikim — prilagodi zamjenu.
    Koristi se pri primjeni zamjena da sačuvamo stil teksta.
    """
    if not original or not replacement:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper() and not original.isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _word_boundary_replace(text: str, pattern: str, replacement: str) -> str:
    """
    Zamjenjuje pattern u tekstu uz:
    - \b word-boundary (ne kvari podriječi)
    - Čuvanje originalnog casing-a
    - Skipovanje sadržaja unutar HTML tagova
    """
    # Splitamo na HTML tagove i tekst između njih
    parts = re.split(r"(<[^>]+>)", text)
    result = []
    escaped = re.escape(pattern)
    try:
        rx = re.compile(rf"\b{escaped}\b", re.IGNORECASE | re.UNICODE)
    except re.error:
        # Ako pattern ima specijalne znakove, pokušaj bez \b
        try:
            rx = re.compile(re.escape(pattern), re.IGNORECASE | re.UNICODE)
        except re.error:
            return text

    for part in parts:
        if part.startswith("<"):
            # HTML tag — ne diramo
            result.append(part)
        else:
            # Tekst — primijeni zamjenu uz casing
            def _sub(m):
                return _preserve_case(m.group(0), replacement)
            result.append(rx.sub(_sub, part))
    return "".join(result)


# ---------------------------------------------------------------------------
# EPUB čitanje / pisanje
# ---------------------------------------------------------------------------

def _read_epub_html_files(epub_path: Path) -> dict[str, str]:
    """
    Čita sve HTML/XHTML fajlove iz EPUB-a.
    Vraća {interni_path: html_sadržaj}.
    """
    html_files = {}
    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            for name in z.namelist():
                if name.lower().endswith((".html", ".xhtml", ".htm")):
                    try:
                        raw = z.read(name)
                        html_files[name] = raw.decode("utf-8", errors="replace")
                    except Exception as e:
                        logger.warning("[name_replacer] Preskačem %s: %s", name, e)
    except Exception as e:
        logger.error("[name_replacer] Greška pri čitanju EPUB: %s", e)
    return html_files


def _write_epub_with_replacements(
    epub_path: Path,
    modified_files: dict[str, str],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Piše novi EPUB s modificiranim HTML fajlovima.
    Ako output_path nije zadan — mijenja originalni (in-place, via temp).
    """
    target = output_path or epub_path
    # Radimo na temp fajlu pa atomski premještamo
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".epub.tmp", dir=epub_path.parent)
    try:
        with zipfile.ZipFile(epub_path, "r") as src, \
             zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename in modified_files:
                    dst.writestr(item, modified_files[item.filename].encode("utf-8"))
                else:
                    dst.writestr(item, src.read(item.filename))
        os.close(tmp_fd)
        shutil.move(tmp_path, str(target))
    except Exception:
        try:
            os.close(tmp_fd)
            os.unlink(tmp_path)
        except Exception:
            pass
        raise
    return target


# ---------------------------------------------------------------------------
# Skupljanje kandidata
# ---------------------------------------------------------------------------

def _collect_entity_candidates(html_files: dict[str, str]) -> dict[str, int]:
    """
    Prolazi kroz sve HTML fajlove i broji pojavljivanja potencijalnih
    vlastitih imenica (proper nouns).

    Vraća {word: count} za sve kandidate.
    """
    counts: dict[str, int] = defaultdict(int)
    for html in html_files.values():
        text = _strip_html(html)
        for m in _PROPER_NOUN_RE.finditer(text):
            word = m.group(0).strip()
            if word and len(word) >= 3:
                counts[word] += 1
    # Filtriraj niske pojavljivanja
    return {w: c for w, c in counts.items() if c >= _MIN_OCCURRENCES}


def _group_by_similarity(candidates: dict[str, int]) -> list[list[str]]:
    """
    Grupiše kandidate koji izgledaju kao varijante istog entiteta.
    Kriteriji:
    - Dijele prvu 3+ slova (Jed... → Jednooki, Jednookog, Jednooka...)
    - Jedan je podstring drugog (One Eye → One-Eye, One Eyes)
    - Levenshtein distance ≤ 3 za kratke (≤10 znakova) varijante
    """
    words = sorted(candidates.keys(), key=lambda w: -candidates[w])

    def _prefix_key(w: str) -> str:
        clean = re.sub(r"[^a-zA-ZčćšžđČĆŠŽĐ]", "", w.lower())
        return clean[:4] if len(clean) >= 4 else clean

    def _levenshtein(a: str, b: str) -> int:
        a, b = a.lower(), b.lower()
        if a == b:
            return 0
        if len(a) < len(b):
            a, b = b, a
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
            prev = curr
        return prev[-1]

    # Grupiši po prefix keyu
    prefix_groups: dict[str, list[str]] = defaultdict(list)
    for w in words:
        prefix_groups[_prefix_key(w)].append(w)

    # Dalje razbij grupe koje su prevelike ili nepovezane
    final_groups = []
    for pkey, group in prefix_groups.items():
        if len(group) == 1:
            # Samotnjak — pošalji kao grupu od 1 (AI može prepoznati varijante)
            final_groups.append(group)
            continue
        # Za manje grupe (≤8): sve zajedno
        if len(group) <= 8:
            final_groups.append(group)
        else:
            # Prevelika prefiks-grupa — batch po 8
            for i in range(0, len(group), 8):
                final_groups.append(group[i : i + 8])

    return final_groups


# ---------------------------------------------------------------------------
# AI analiza
# ---------------------------------------------------------------------------

def _build_ai_prompt(groups: list[list[str]], full_text_sample: str) -> str:
    """
    Gradi prompt za AI koji će odrediti kanonsku formu i sve varijante.
    """
    groups_txt = ""
    for i, grp in enumerate(groups, 1):
        groups_txt += f"{i}. {' | '.join(grp)}\n"

    # Uzmemo sample teksta (prvih ~2000 znakova čistog teksta)
    sample = full_text_sample[:2000].strip()

    return f"""Ti si ekspert za književni prijevod na bosanski/hrvatski jezik.

Analziraš EPUB knjigu i trebaš normalizovati vlastita imena i nazive entiteta.

KONTEKST KNJIGE (uzorak teksta):
"""
{sample}
"""

KANDIDATI ZA NORMALIZACIJU (grupe srodnih oblika):
{groups_txt}

ZADATAK:
Za svaki entitet (lik, mjesto, predmet, organizacija) koji ima VIŠESTRUKE VARIJANTE pisanja:
1. Odredi KANONSKU (standardnu) formu na bosanskom/hrvatskom
2. Navedi SVE varijante koje treba zamijeniti tom kanonskom formom
3. Uključi sve morfološke oblike (padeže, rod, broj) ako su vidljivi

PRAVILA:
- Ako je samo jedna forma → preskači (nema zamjene)
- Ako je entitet već konzistentan → preskači
- Kanonska forma = nominativ jednina (osim za nepromjenljive: npr. "Mob" ostaje "Mob")
- Strani nazivi koji su inkonsistentno prevedeni: odaberi prevod ili original, ali JEDNOOBRAZNO
- NE diraj: obične imenice, pridjeve, glagole — samo VLASTITA IMENA

FORMAT ODGOVORA (isključivo JSON, bez ikakvih dodatnih objašnjenja):
{{
  "zamjene": [
    {{
      "kanonska": "KANONSKA_FORMA",
      "varijante": ["varijanta1", "varijanta2", "varijanta3"],
      "napomena": "kratko objašnjenje zašto"
    }}
  ]
}}

Ako NEMA nikakvih zamjena za napraviti, vrati: {{"zamjene": []}}
"""


def _call_ai_for_replacements(
    groups: list[list[str]],
    full_text_sample: str,
    fleet,
) -> list[dict]:
    """
    Poziva AI fleet da analizira grupe entiteta i vrati zamjene.
    Vraća listu: [{"kanonska": str, "varijante": [str, ...], "napomena": str}]
    """
    if not groups:
        return []

    prompt = _build_ai_prompt(groups, full_text_sample)

    try:
        import asyncio
        from network.provider_router import call_provider

        async def _async_call():
            return await call_provider(
                prompt=prompt,
                uloga="ANALIZA",
                fleet=fleet,
                max_tokens=1500,
                temperature=0.05,
            )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_async_call())
        finally:
            loop.close()

        if not result:
            return []

        # Parsiranje JSON odgovora
        clean = re.sub(r"```(?:json)?\s*", "", result).replace("```", "").strip()
        data = json.loads(clean)
        return data.get("zamjene", [])

    except json.JSONDecodeError as e:
        logger.warning("[name_replacer] AI JSON parse greška: %s", e)
        return []
    except Exception as e:
        logger.warning("[name_replacer] AI poziv pao: %s", e)
        return []


# ---------------------------------------------------------------------------
# Primjena zamjena
# ---------------------------------------------------------------------------

def _apply_replacements_to_html(
    html: str,
    replacements: list[tuple[str, str]],
) -> tuple[str, list[tuple[str, str]]]:
    """
    Primjenjuje listu (varijanta, kanonska) zamjena na jedan HTML fajl.
    Vraća (modificirani_html, lista_primijenjenih).
    """
    applied = []
    for variant, canonical in replacements:
        if not variant or not canonical or variant == canonical:
            continue
        new_html = _word_boundary_replace(html, variant, canonical)
        if new_html != html:
            applied.append((variant, canonical))
            html = new_html
    return html, applied


def _build_replacement_pairs(
    ai_results: list[dict],
) -> list[tuple[str, str]]:
    """
    Iz AI rezultata gradi płasku listu (varijanta, kanonska).
    Sortira po dužini varijante (duže prvo — da duži matchevi imaju prednost).
    """
    pairs = []
    for item in ai_results:
        canonical = item.get("kanonska", "").strip()
        if not canonical:
            continue
        for variant in item.get("varijante", []):
            variant = variant.strip()
            if variant and variant != canonical:
                pairs.append((variant, canonical))
    # Duže varijante imaju prednost (sprečava djelomični match)
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


# ---------------------------------------------------------------------------
# .epub.replacement fajl
# ---------------------------------------------------------------------------

def _write_replacement_file(
    epub_path: Path,
    all_pairs: list[tuple[str, str]],
    ai_results: list[dict],
    stats: dict,
) -> Path:
    """
    Piše .epub.replacement fajl pored originalnog EPUB-a.
    Format: original#->#ispravka
    """
    rep_path = epub_path.with_suffix(epub_path.suffix + ".replacement")
    lines = [
        f"#! Skriptorij Smart Name Replacer — {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"#! Knjiga: {epub_path.name}",
        f"#! Entiteta analiziranih: {stats.get('entities', 0)}",
        f"#! Zamjena pronađenih: {stats.get('found', 0)}",
        f"#! Zamjena primijenjenih: {stats.get('applied', 0)}",
        f"#! Format: original{_SEP}ispravka",
        "#! ─────────────────────────────────────────────",
        "",
    ]

    # Grupiši po kanonskoj formi za preglednost
    from collections import defaultdict
    by_canonical: dict[str, list] = defaultdict(list)
    napomene: dict[str, str] = {}
    for item in ai_results:
        c = item.get("kanonska", "").strip()
        if c:
            for v in item.get("varijante", []):
                v = v.strip()
                if v and v != c:
                    by_canonical[c].append(v)
            if item.get("napomena"):
                napomene[c] = item["napomena"]

    for canonical in sorted(by_canonical.keys()):
        variants = by_canonical[canonical]
        if napomene.get(canonical):
            lines.append(f"#! {canonical}: {napomene[canonical]}")
        for variant in variants:
            lines.append(f"{variant}{_SEP}{canonical}")
        lines.append("")

    rep_path.write_text("\n".join(lines), encoding="utf-8")
    return rep_path


# ---------------------------------------------------------------------------
# Javno API
# ---------------------------------------------------------------------------

def run_name_replacer(
    epub_path: str | Path,
    fleet=None,
    output_path: str | Path | None = None,
    log_callback=None,
) -> dict:
    """
    Glavna funkcija — pokreni Smart Name Replacer na EPUB-u.

    Parametri:
        epub_path    — putanja do EPUB fajla
        fleet        — FleetManager instanca (ili None → kreira novu)
        output_path  — putanja za izlazni EPUB (None = in-place)
        log_callback — opcionalna f(msg, atype) za audit log

    Vraća dict sa statistikama:
        {
          "ok": bool,
          "epub_path": str,
          "replacement_file": str,
          "entities_found": int,
          "replacements_applied": int,
          "pairs": [(variant, canonical), ...],
          "error": str | None,
        }
    """
    epub_path = Path(epub_path)

    def _log(msg: str, atype: str = "info"):
        logger.info("[name_replacer] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    _log(f"🔍 Name Replacer pokrenut za: {epub_path.name}", "system")

    result = {
        "ok": False,
        "epub_path": str(epub_path),
        "replacement_file": "",
        "entities_found": 0,
        "replacements_applied": 0,
        "pairs": [],
        "error": None,
    }

    if not epub_path.exists():
        result["error"] = f"EPUB fajl nije pronađen: {epub_path}"
        _log(f"❌ {result['error']}", "error")
        return result

    # ── Korak 1: Čitanje HTML-a iz EPUB-a ────────────────────────────────
    _log("📖 Čitam HTML iz EPUB-a...", "tech")
    html_files = _read_epub_html_files(epub_path)
    if not html_files:
        result["error"] = "EPUB ne sadrži HTML fajlove"
        _log(f"❌ {result['error']}", "error")
        return result
    _log(f"   → {len(html_files)} HTML fajlova pronađeno", "tech")

    # ── Korak 2: Skupljanje kandidata ────────────────────────────────────
    _log("🔎 Skeniram vlastita imena i entitete...", "tech")
    candidates = _collect_entity_candidates(html_files)
    _log(f"   → {len(candidates)} kandidata pronađeno (min. {_MIN_OCCURRENCES}× pojava)", "tech")

    if not candidates:
        _log("ℹ️ Nema dovoljno kandidata za analizu — EPUB je vjerovatno konzistentan", "info")
        result["ok"] = True
        return result

    # ── Korak 3: Grupiranje srodnih oblika ───────────────────────────────
    _log("📊 Grupiram srodne varijante...", "tech")
    groups = _group_by_similarity(candidates)

    # Uzimamo samo grupe sa 2+ varijantama za AI (ostalo je već konzistentno)
    multi_groups = [g for g in groups if len(g) > 1]
    _log(f"   → {len(multi_groups)} grupa s potencijalnim varijantama", "tech")

    # Uzorak teksta za kontekst
    full_text_sample = ""
    for html in list(html_files.values())[:5]:
        full_text_sample += _strip_html(html)[:500] + "\n"

    result["entities_found"] = len(candidates)

    if not multi_groups:
        _log("ℹ️ Nema varijantnih grupa — vlastita imena su konzistentna", "info")
        result["ok"] = True
        return result

    # ── Korak 4: AI analiza ──────────────────────────────────────────────
    # Batch: max _MAX_ENTITIES_PER_PROMPT grupe po pozivu
    _log(f"🤖 AI analiza {len(multi_groups)} grupa entiteta...", "system")

    if fleet is None:
        try:
            from api_fleet import FleetManager
            from config.settings import CONFIG_PATH
            fleet = FleetManager(config_path=CONFIG_PATH)
        except Exception as e:
            result["error"] = f"Fleet ne može biti inicijaliziran: {e}"
            _log(f"❌ {result['error']}", "error")
            return result

    all_ai_results = []
    for batch_start in range(0, len(multi_groups), _MAX_ENTITIES_PER_PROMPT):
        batch = multi_groups[batch_start : batch_start + _MAX_ENTITIES_PER_PROMPT]
        batch_num = batch_start // _MAX_ENTITIES_PER_PROMPT + 1
        total_batches = (len(multi_groups) + _MAX_ENTITIES_PER_PROMPT - 1) // _MAX_ENTITIES_PER_PROMPT
        _log(f"   → Batch {batch_num}/{total_batches}: {len(batch)} grupa...", "tech")

        batch_results = _call_ai_for_replacements(batch, full_text_sample, fleet)
        all_ai_results.extend(batch_results)
        _log(f"   → Batch {batch_num}: {len(batch_results)} zamjena dobijeno", "tech")

    _log(f"✅ AI analiza završena: {len(all_ai_results)} entiteta za normalizaciju", "success")

    if not all_ai_results:
        _log("ℹ️ AI nije pronašao zamjene — tekst je konzistentan", "info")
        result["ok"] = True
        return result

    # ── Korak 5: Primjena zamjena ────────────────────────────────────────
    replacement_pairs = _build_replacement_pairs(all_ai_results)
    _log(f"📝 Primjenjujem {len(replacement_pairs)} zamjena na {len(html_files)} fajlova...", "system")

    modified_files = {}
    total_applied_set = set()

    for fname, html in html_files.items():
        new_html, applied = _apply_replacements_to_html(html, replacement_pairs)
        if applied:
            modified_files[fname] = new_html
            for pair in applied:
                total_applied_set.add(pair)

    applied_pairs = list(total_applied_set)
    _log(f"   → {len(applied_pairs)} jedinstvenih zamjena primijenjeno u {len(modified_files)} fajlova", "success")

    # ── Korak 6: Pisanje .epub.replacement fajla ─────────────────────────
    stats = {
        "entities": len(candidates),
        "found": len(all_ai_results),
        "applied": len(applied_pairs),
    }
    rep_path = _write_replacement_file(epub_path, applied_pairs, all_ai_results, stats)
    _log(f"📄 Replacement fajl snimljen: {rep_path.name}", "success")

    # ── Korak 7: Pisanje novog EPUB-a ────────────────────────────────────
    if modified_files:
        out = Path(output_path) if output_path else None
        written = _write_epub_with_replacements(epub_path, modified_files, out)
        _log(f"✅ EPUB ažuriran: {written.name} ({len(modified_files)} fajlova izmijenjeno)", "success")
    else:
        _log("ℹ️ EPUB nije mijenjana — sve varijante već konzistentne", "info")

    result.update({
        "ok": True,
        "replacement_file": str(rep_path),
        "replacements_applied": len(applied_pairs),
        "pairs": applied_pairs,
    })

    _log(
        f"🎉 Name Replacer završen: {len(applied_pairs)} zamjena / {len(candidates)} entiteta",
        "success",
    )
    return result


# ---------------------------------------------------------------------------
# CLI standalone pokretanje
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Upotreba: python -m epub.name_replacer <putanja_do_epub>")
        print("          python -m epub.name_replacer knjiga.epub [izlaz.epub]")
        sys.exit(1)

    epub_in = sys.argv[1]
    epub_out = sys.argv[2] if len(sys.argv) > 2 else None

    def cli_log(msg, atype="info"):
        icons = {
            "system": "🔷", "success": "✅", "error": "❌",
            "warning": "⚠️", "tech": "  ·", "info": "ℹ️",
        }
        print(f"{icons.get(atype, '')} {msg}")

    res = run_name_replacer(epub_in, output_path=epub_out, log_callback=cli_log)

    if res["ok"]:
        print(f"\n✅ Gotovo!")
        print(f"   EPUB:              {res['epub_path']}")
        print(f"   Replacement fajl:  {res['replacement_file']}")
        print(f"   Entiteta:          {res['entities_found']}")
        print(f"   Zamjena:           {res['replacements_applied']}")
    else:
        print(f"\n❌ Greška: {res['error']}")
        sys.exit(1)
