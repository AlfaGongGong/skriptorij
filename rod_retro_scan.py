#!/usr/bin/env python3
"""
rod_retro_scan.py — Booklyfi/Skriptorij
════════════════════════════════════════════════════════════════════════
Retroaktivni scanner i fixer rodovnih grešaka u svim .chk fajlovima.

UPOTREBA:
    python rod_retro_scan.py --scan              # samo prikaži greške
    python rod_retro_scan.py --fix               # ispravi greške (regex)
    python rod_retro_scan.py --fix --ai          # ispravi greške (regex + AI)
    python rod_retro_scan.py --fix --dry-run     # prikaži što bi se promijenilo
    python rod_retro_scan.py --stats             # statistika bez izmjena
    python rod_retro_scan.py --knjiga KNJIGA     # filtriraj po knjizi
    python rod_retro_scan.py --prag 7.0          # skenira samo chunkove s ocjenom < prag

Fajlovi se mijenjaju in-place s .bak backup kopijom.
════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rod_retro")

# ── Konfiguracija ──────────────────────────────────────────────────────────────
try:
    from config.settings import CHECKPOINT_BASE
except ImportError:
    CHECKPOINT_BASE = Path(os.environ.get(
        "SKRIPTORIJ_CHK",
        "/storage/emulated/0/booklyfi_checkpoints"
    ))

CHECKPOINT_BASE = Path(CHECKPOINT_BASE)

# ── Rodovni regex patterne ─────────────────────────────────────────────────────
# Svaki tuple: (pattern, opis, fn_ispravak)
# fn_ispravak prima match i vraća ispravljeni string ili None (ako ne može auto)

def _zamijeni_gpr_zena(m: re.Match) -> str:
    """Ženski subj + muški GPR — zamijeni završetak."""
    cijela = m.group(0)
    gpr = m.group(2)
    # -ao → -ala, -io → -ila, -eo → -ela, -o → -la
    if gpr.endswith("ao"):
        novi = gpr[:-2] + "ala"
    elif gpr.endswith("io"):
        novi = gpr[:-2] + "ila"
    elif gpr.endswith("eo"):
        novi = gpr[:-2] + "ela"
    elif gpr.endswith("o") and not gpr.endswith("lo"):
        novi = gpr[:-1] + "la"
    else:
        return cijela  # ne može auto
    return m.group(1) + novi

def _zamijeni_gpr_muskarac(m: re.Match) -> str:
    """Muški subj + ženski GPR — zamijeni završetak."""
    cijela = m.group(0)
    gpr = m.group(2)
    if gpr.endswith("ala"):
        novi = gpr[:-3] + "ao"
    elif gpr.endswith("ila"):
        novi = gpr[:-3] + "io"
    elif gpr.endswith("ela"):
        novi = gpr[:-3] + "eo"
    elif gpr.endswith("la"):
        novi = gpr[:-2] + "o"
    else:
        return cijela
    return m.group(1) + novi

# Lista: (compiled_pattern, opis, tip)
ROD_PATTERNE: list[tuple[re.Pattern, str, str]] = [
    # Ona je + muški GPR (završetak -o, -ao, -io, -eo)
    (
        re.compile(
            r"(?<![A-Za-zČčŠšŽžĐđĆćÄäÖöÜü])(?<!\w)(ona\s+je\s+|ona\s+(?:nije|nije\s+bila)\s+)(\w+(?:ao|io|eo|[^al]o))\b",
            re.IGNORECASE
        ),
        "Ženski subj (ona) + muški GPR",
        "zena_gpr",
    ),
    # Bila je + muški GPR
    (
        re.compile(
            r"(bila\s+je\s+)(\w+(?:ao|io|[^aeio]eo))\b",
            re.IGNORECASE
        ),
        "Ženski subj (bila) + muški GPR",
        "zena_gpr",
    ),
    # On je + ženski GPR (završetak -la, -ila, -ala, -ela)
    (
        re.compile(
            r"(?<![A-Za-zČčŠšŽžĐđĆćÄäÖöÜü])(?<!\w)(on\s+je\s+|on\s+(?:nije|nije\s+bio)\s+)(\w+(?:ala|ila|ela|[^i]la))\b",
            re.IGNORECASE
        ),
        "Muški subj (on) + ženski GPR",
        "muskarac_gpr",
    ),
    # Bio je + ženski GPR
    (
        re.compile(
            r"(bio\s+je\s+)(\w+(?:ala|ila|ela|[^i]la))\b",
            re.IGNORECASE
        ),
        "Muški subj (bio) + ženski GPR",
        "muskarac_gpr",
    ),
    # Bila je + muški pridjev (-an, -en, -an oblici)
    (
        re.compile(
            r"\b(bila\s+je\s+)(\w{4,}(?:an|en))\b",
            re.IGNORECASE
        ),
        "Bila + muški pridjev (-an/-en)",
        "pridjev_zena",
    ),
    # Bio je + ženski pridjev (-na, -ena, -ana oblici)
    (
        re.compile(
            r"\b(bio\s+je\s+)(\w{4,}(?:ena|ana|ina))\b",
            re.IGNORECASE
        ),
        "Bio + ženski pridjev (-na/-ena)",
        "pridjev_muskarac",
    ),
]

# Whitelist — ispravni oblici koji triggiraju regex ali su OK
WHITELIST: set[str] = {
    # Prilozi i čestice koji završavaju na -o (nisu GPR)
    "samo", "kako", "tako", "jako", "malo", "vrlo", "jako", "svo",
    "tamo", "ovamo", "onamo", "gdje", "kamo", "odakle", "otkamo",
    "rano", "kasno", "čisto", "pravo", "desno", "lijevo", "blago",
    "opet", "često", "rijetko", "uvijek", "nikad", "odmah", "već",
    "kao", "nego", "već", "upravo", "baš", "tek", "još", "ipak",
    "isto", "drugačije", "inače", "naravno", "zapravo", "zaista",
    "doista", "očito", "jasno", "sigurno", "svakako", "naročito",
    "posebno", "osobito", "iznimno", "izuzetno", "iznenada", "napokon",
    "konačno", "ponovno", "ponovo", "ujedno", "zajedno", "odjednom",
    "iznenada", "pogotovo", "pogotovu", "međutim", "međusobno",
    "podjednako", "ravnomjerno", "ravnopravno", "ravnodušno",
    # Pridjevi u neutralnom rodu koji mogu stajati uz ženski subj
    "jasno", "točno", "sigurno", "čudno", "zanimljivo", "nevjerojatno",
    # Česte imenice na -o koje nisu GPR
    "čudo", "nebo", "pero", "vino", "meso", "tijelo", "selo", "polje",

    # Još priloga i zamjenica koji triggiraju regex
    "isključivo", "gotovo", "jednako", "netko", "nitko", "nešto",
    "ništa", "svašta", "neko", "nikо", "sve", "svako", "mnogo",
    "malo", "puno", "dosta", "dovoljno", "previše", "premalo",
    "toliko", "koliko", "onoliko", "ovoliko", "otprilike",
    "zbilja", "stvarno", "uistinu", "doduše", "možda", "valjda",
    "vjerojatno", "vjerovatno", "sigurno", "nužno", "moguće",
    "potrebno", "važno", "vrijedno", "korisno", "beskorisno",
    "teško", "lako", "lijepo", "ružno", "mirno", "tiho", "glasno",
    "brzo", "sporo", "polako", "naglo", "iznenada", "nažalost",
    "srećom", "slučajno", "namjerno", "uzalud", "uzaludo",
    # Pridjevi sr. roda uz ženski subj (npr. "bila je poznato") — greška je moguća
    # ali ne može se auto-ispraviti — isključi iz GPR patterна
    "poznato", "rečeno", "napravljeno", "urađeno", "riješeno",
    "završeno", "određeno", "dozvoljeno", "zabranjeno", "dogovoreno",
    "planirano", "predviđeno", "naređeno", "odlučeno", "zamišljeno",

    # Imenice i prilozi na -o/-ao koji se krivo detektiraju
    "oko", "uho", "pero", "kolo", "čelo", "tlo", "zlo", "dobro",
    "tamno", "bijelo", "crno", "crveno", "zeleno", "plavo", "žuto",
    "pješčano", "savršeno", "čvrsto", "meko", "tvrdo", "glatko",
    "duboko", "plitko", "visoko", "nisko", "široko", "usko",
    "daleko", "blizu", "blisko", "skoro", "skupa", "skupo", "jeftino",
    "toplo", "hladno", "vruće", "studeno", "mokro", "suho",
    "puno", "prazno", "teško", "lagano", "ravno", "krivo",
    "točno", "netočno", "ispravno", "pogrešno", "slobodno",
    "mirno", "nemirno", "tiho", "glasno", "jasno", "mutno",
    "čisto", "prljavo", "uredno", "neuredno", "lijepo", "ružno",
    "dobro", "loše", "zlo", "pravo", "krivo", "prosto", "složeno",
    "sigurno", "opasno", "korisno", "beskorisno", "vrijedno",
    "moguće", "nemoguće", "potrebno", "nepotrebno", "nužno",
    "zanimljivo", "dosadno", "čudno", "normalno", "uobičajeno",
    "važno", "nevažno", "poznato", "nepoznato", "vidljivo",
    "plijen", "rješenje", "mišljenje", "viđenje", "osjećanje",
    "saznanje", "otkriće", "iskustvo", "znanje", "obrazovanje",
    "oko", "lice", "tijelo", "srce", "rame", "koljeno", "bedro",
    "more", "polje", "brdo", "selo", "mjesto", "središte",
    "dno", "dno", "ogledalo", "staklo", "zlato", "srebro",

    # GPR koji završavaju na -o a nisu muški GPR
    "rečeno", "napravljeno", "urađeno", "završeno", "početo", "otvoreno",
    "zatvoreno", "određeno", "prikazano", "napisano", "poznato", "dano",
    "uzeto", "dato", "plaćeno", "pitano", "rješeno", "riješeno",
    # Pridjevi koji izgledaju kao ženski ali su OK u određenim kontekstima
    "hrana", "rana", "tama", "drama", "scena", "tema", "forma", "norma",
    "mana", "zona", "klima", "škola", "žena", "sjena", "cijena", "strana",
    # Glagoli koji završavaju -na ali nisu pridjevi
    "ostala", "prošla", "došla", "otišla", "ušla", "izašla",
    # Preostali false-positivi — imenice i prilozi na -o
    "oko", "uho", "pero", "kolo", "čelo", "tlo", "zlo", "dobro",
    "tamno", "bijelo", "crno", "crveno", "zeleno", "plavo", "žuto",
    "pješčano", "savršeno", "čvrsto", "meko", "tvrdo", "glatko",
    "duboko", "plitko", "visoko", "nisko", "široko", "usko",
    "daleko", "blisko", "skoro", "skupo", "jeftino",
    "toplo", "hladno", "mokro", "suho", "puno", "prazno",
    "teško", "lagano", "ravno", "krivo", "točno", "ispravno",
    "slobodno", "mirno", "tiho", "glasno", "jasno", "mutno",
    "čisto", "prljavo", "uredno", "lijepo", "ružno",
    "sigurno", "opasno", "korisno", "vrijedno", "moguće",
    "nemoguće", "potrebno", "nužno", "zanimljivo", "dosadno",
    "čudno", "normalno", "važno", "poznato", "vidljivo",
    "isključivo", "gotovo", "jednako", "netko", "nitko",
    "nešto", "ništa", "svašta", "mnogo", "dosta", "dovoljno",
    "previše", "toliko", "koliko", "otprilike", "zbilja",
    "stvarno", "doduše", "možda", "valjda", "vjerovatno",
    "vjerojatno", "naravno", "zapravo", "zaista", "doista",
    "naročito", "posebno", "osobito", "iznimno", "izuzetno",
    "napokon", "konačno", "ujedno", "zajedno", "odjednom",
    "pogotovo", "međutim", "podjednako", "ravnomjerno",
    "plijen", "rješenje", "mišljenje", "viđenje", "osjećanje",
    "saznanje", "otkriće", "iskustvo", "znanje", "more",
    "polje", "brdo", "selo", "mjesto", "središte", "dno",
    "ogledalo", "staklo", "zlato", "srebro", "tijelo", "srce",
    "pedala",  # imenica (dio bicikla), ne glagol
}

def _je_whitelisted(rijec: str) -> bool:
    r = rijec.strip()
    # Vlastita imena (veliko početno slovo, >2 slova) nisu GPR greška
    if len(r) > 2 and r[0].isupper() and r[1:].islower():
        return True
    return r.lower() in WHITELIST

# ── Dataclass za nalaz ────────────────────────────────────────────────────────

@dataclass
class RodovnaGreska:
    chunk_fajl: Path
    pozicija: int
    kontekst: str
    opis: str
    tip: str
    original: str
    prijedlog: Optional[str]
    score: float = 0.0
    knjiga: str = ""


@dataclass
class ScanRezultat:
    ukupno_chk: int = 0
    skenirano: int = 0
    greske: list[RodovnaGreska] = field(default_factory=list)
    ispravljeno: int = 0
    preskoceno: int = 0
    greske_zapisa: int = 0


# ── Core scanner ──────────────────────────────────────────────────────────────

def skeniraj_tekst(tekst: str, chunk_fajl: Path, score: float, knjiga: str) -> list[RodovnaGreska]:
    """Skenira tekst i vraća listu rodovnih grešaka."""
    nalazi: list[RodovnaGreska] = []
    # Ukloni HTML tagove za analizu (ali čuvaj original za ispravak)
    cist = re.sub(r"<[^>]+>", " ", tekst)

    for pattern, opis, tip in ROD_PATTERNE:
        for m in pattern.finditer(cist):
            # Provjeri whitelist
            pogodak = m.group(0)
            rijeci = pogodak.split()
            if any(_je_whitelisted(r) for r in rijeci):
                continue
            # Odbaci ako je subjekat zapravo vlastito ime (veliko slovo ispred match-a)
            poz = m.start()
            prethodni = tekst[max(0, poz-40):poz]
            zadnja_rijec = re.search(r'(\S+)\s*$', prethodni)
            if zadnja_rijec:
                zr = zadnja_rijec.group(1).strip('.,;:!?—–- ')
                # Ako zadnja riječ ispred "on/ona/bio/bila" počinje velikim slovom
                # i nije na whitelisti zamjenica — preskači (vlastito ime kao subj)
                ZAMJENICE = {"on", "ona", "bio", "bila", "nije", "je"}
                if (len(zr) > 2 and zr[0].isupper()
                        and zr.lower() not in ZAMJENICE
                        and not zr[0].isdigit()):
                    continue

            # Kontekst (okolnih 60 znakova)
            start = max(0, m.start() - 60)
            end = min(len(cist), m.end() + 60)
            kontekst = "..." + cist[start:end].replace("\n", " ") + "..."

            # Prijedlog ispravka
            prijedlog = None
            if tip == "zena_gpr":
                try:
                    prijedlog = _zamijeni_gpr_zena(m)
                except Exception:
                    pass
            elif tip == "muskarac_gpr":
                try:
                    prijedlog = _zamijeni_gpr_muskarac(m)
                except Exception:
                    pass

            nalazi.append(RodovnaGreska(
                chunk_fajl=chunk_fajl,
                pozicija=m.start(),
                kontekst=kontekst,
                opis=opis,
                tip=tip,
                original=pogodak,
                prijedlog=prijedlog if prijedlog != pogodak else None,
                score=score,
                knjiga=knjiga,
            ))

    return nalazi


def ucitaj_chunk(chk_fajl: Path) -> tuple[Optional[dict], float]:
    """Čita .chk fajl — podržava JSON i pseudo-JSON s tipografskim navodnicima."""
    try:
        raw = chk_fajl.read_text(encoding="utf-8")

        # Pokušaj 1: standardni JSON (strict=False za kontrolne znakove)
        try:
            normed = raw.replace("\u201e", chr(34)).replace("\u201c", chr(34)).replace("\u201d", chr(34))
            data = json.loads(normed, strict=False)
            score = float(data.get("score", 10.0))
            return data, score
        except Exception:
            pass

        # Pokušaj 2: regex ekstrakcija ključnih polja iz pseudo-JSON-a
        # Izvuci score
        score = 10.0
        m_score = re.search(r'["„“]score["”“]\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw)
        if m_score:
            score = float(m_score.group(1))

        # Izvuci sadrzaj/korektura — sve između prvog " nakon ključa do kraja }
        tekst = ""
        for kljuc in ("korektura", "sadrzaj"):
            pattern = re.compile(
                r'[\u201e\u201c"]' + kljuc + r'[\u201d\u201c"]\s*:\s*"(.*?)(?="\s*(?:,\s*[\u201e\u201c"\w]|\}))',
                re.DOTALL
            )
            m = pattern.search(raw)
            if m:
                tekst = m.group(1)
                break

        if not tekst:
            # Pokušaj 3: uzmi sve između prvog " i zadnjeg "
            m_brute = re.search(r':\s*"\n?(.*)', raw, re.DOTALL)
            if m_brute:
                tekst = m_brute.group(1).rstrip().rstrip('}').rstrip('"').rstrip()

        if not tekst or len(tekst.strip()) < 10:
            return None, 0.0

        data = {"korektura": tekst, "score": score}
        return data, score

    except Exception as e:
        log.warning(f"Ne mogu čitati {chk_fajl.name}: {e}")
        return None, 0.0

def skeniraj_sve(
    knjiga_filter: Optional[str] = None,
    score_prag: float = 11.0,
    max_chk: int = 99999,
) -> ScanRezultat:
    """Skenira sve .chk fajlove u CHECKPOINT_BASE."""
    rezultat = ScanRezultat()

    if not CHECKPOINT_BASE.exists():
        log.error(f"Checkpoint direktorij ne postoji: {CHECKPOINT_BASE}")
        return rezultat

    chk_fajlovi = sorted(CHECKPOINT_BASE.rglob("*.chk"))
    rezultat.ukupno_chk = len(chk_fajlovi)
    log.info(f"Pronađeno {rezultat.ukupno_chk} .chk fajlova u {CHECKPOINT_BASE}")

    for chk in chk_fajlovi[:max_chk]:
        knjiga = chk.parent.name

        if knjiga_filter and knjiga_filter.lower() not in knjiga.lower():
            continue

        data, score = ucitaj_chunk(chk)
        if data is None:
            rezultat.greske_zapisa += 1
            continue

        if score > score_prag:
            continue  # preskači dobre chunkove

        tekst = data.get("korektura", data.get("korektura", data.get("sadrzaj", "")))
        if not tekst or len(tekst.strip()) < 20:
            continue

        rezultat.skenirano += 1
        greske = skeniraj_tekst(tekst, chk, score, knjiga)
        rezultat.greske.extend(greske)

    log.info(f"Skenirano: {rezultat.skenirano} chunkova | "
             f"Rodovnih grešaka: {len(rezultat.greske)}")
    return rezultat


# ── Fixer ─────────────────────────────────────────────────────────────────────

def ispravi_chunk_regex(chk_fajl: Path, dry_run: bool = False) -> tuple[int, str]:
    """
    Primjenjuje regex ispravke na jedan .chk fajl.
    Vraća (broj_izmjena, novi_tekst).
    """
    data, score = ucitaj_chunk(chk_fajl)
    if data is None:
        return 0, ""

    tekst = data.get("korektura", data.get("korektura", data.get("sadrzaj", "")))
    if not tekst:
        return 0, ""

    # Primijeni regex na čisti tekst (bez HTML)
    cist = re.sub(r"<[^>]+>", " ", tekst)
    broj_izmjena = 0
    novi_tekst = tekst

    for pattern, opis, tip in ROD_PATTERNE:
        for m in pattern.finditer(cist):
            original = m.group(0)
            rijeci = original.split()
            if any(_je_whitelisted(r) for r in rijeci):
                continue
            # Odbaci ako je subjekat zapravo vlastito ime (veliko slovo ispred match-a)
            poz = m.start()
            prethodni = tekst[max(0, poz-40):poz]
            zadnja_rijec = re.search(r'(\S+)\s*$', prethodni)
            if zadnja_rijec:
                zr = zadnja_rijec.group(1).strip('.,;:!?—–- ')
                # Ako zadnja riječ ispred "on/ona/bio/bila" počinje velikim slovom
                # i nije na whitelisti zamjenica — preskači (vlastito ime kao subj)
                ZAMJENICE = {"on", "ona", "bio", "bila", "nije", "je"}
                if (len(zr) > 2 and zr[0].isupper()
                        and zr.lower() not in ZAMJENICE
                        and not zr[0].isdigit()):
                    continue

            prijedlog = None
            if tip == "zena_gpr":
                try:
                    prijedlog = _zamijeni_gpr_zena(m)
                except Exception:
                    continue
            elif tip == "muskarac_gpr":
                try:
                    prijedlog = _zamijeni_gpr_muskarac(m)
                except Exception:
                    continue

            if prijedlog and prijedlog != original:
                # Zamijeni u originalnom HTML tekstu (case-insensitive)
                novi_tekst = re.sub(
                    re.escape(original),
                    prijedlog,
                    novi_tekst,
                    count=1,
                    flags=re.IGNORECASE,
                )
                broj_izmjena += 1
                log.debug(f"  {original!r} → {prijedlog!r}")

    if broj_izmjena > 0 and not dry_run:
        # Backup + write
        backup = chk_fajl.with_suffix(f".bak_rod_{int(time.time())}")
        chk_fajl.rename(backup)
        data["korektura"] = novi_tekst
        data["rod_retro"] = {
            "datum": datetime.utcnow().isoformat(),
            "izmjena": broj_izmjena,
        }
        chk_fajl.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return broj_izmjena, novi_tekst


def ispravi_chunk_ai(
    chk_fajl: Path,
    api_key: str,
    dry_run: bool = False,
) -> tuple[int, str]:
    """
    AI ispravak rodovnih grešaka za jedan chunk.
    Koristi Gemini Flash (isti kao morfo_validator).
    """
    data, score = ucitaj_chunk(chk_fajl)
    if data is None:
        return 0, ""

    tekst = data.get("korektura", data.get("korektura", data.get("sadrzaj", "")))
    if not tekst or len(tekst.strip()) < 30:
        return 0, ""

    sys_prompt = """Ti si precizni lektor za bosanski/hrvatski jezik.
JEDINI ZADATAK: Ispravi greške u rodovnom slaganju GPR-a i predikatnih pridjeva.

PRAVILA:
- Muški subj → GPR na -o/-ao/-io | pridjev na -an/-en
- Ženski subj → GPR na -la/-ila/-ala | pridjev na -na/-ena
- Srednji subj → GPR na -lo/-ilo/-alo
- NE mijenjaj ništa drugo osim rodovnog slaganja.
- Broj rečenica ostaje isti. HTML tagovi ostaju nepromijenjeni.

PRIMJERI GREŠKE → ISPRAVKA:
  "Ona je rekao" → "Ona je rekla"
  "Bio je umorna" → "Bio je umoran"
  "Bila je siguran" → "Bila je sigurna"

Vrati ISKLJUČIVO JSON:
{"tekst": "<cijeli ispravljeni tekst>", "izmjene": [{"original": "...", "ispravak": "...", "objasnjenje": "rod"}]}
Ako nema grešaka: {"tekst": "<original nepromijenjen>", "izmjene": []}"""

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=sys_prompt,
        )
        cfg = genai.types.GenerationConfig(
            temperature=0.05,
            max_output_tokens=len(tekst) * 2 + 500,
            response_mime_type="application/json",
        )
        odg = model.generate_content(
            f"Analiziraj i ispravi rodovne greške:\n\n---\n{tekst}\n---\n\nVrati JSON.",
            generation_config=cfg,
        )
        raw = odg.text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        novi_tekst = parsed.get("tekst", tekst)
        izmjene = parsed.get("izmjene", [])

        if len(novi_tekst) < len(tekst) * 0.7:
            log.warning(f"AI vratio drastično kraći tekst za {chk_fajl.name} — odbacujem")
            return 0, tekst

        if izmjene and not dry_run:
            backup = chk_fajl.with_suffix(f".bak_rod_ai_{int(time.time())}")
            chk_fajl.rename(backup)
            data["korektura"] = novi_tekst
            data["rod_retro_ai"] = {
                "datum": datetime.utcnow().isoformat(),
                "izmjena": len(izmjene),
            }
            chk_fajl.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return len(izmjene), novi_tekst

    except Exception as e:
        log.error(f"AI greška za {chk_fajl.name}: {e}")
        return 0, tekst


# ── Izvještaj ─────────────────────────────────────────────────────────────────

def ispisi_izvjestaj(rezultat: ScanRezultat, verbose: bool = False) -> None:
    print(f"\n{'═' * 64}")
    print(f"  ROD_RETRO_SCAN — Izvještaj  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═' * 64}")
    print(f"  Ukupno .chk fajlova : {rezultat.ukupno_chk}")
    print(f"  Skenirano           : {rezultat.skenirano}")
    print(f"  Rodovnih grešaka    : {len(rezultat.greske)}")
    print(f"  Ispravljeno         : {rezultat.ispravljeno}")
    print(f"  Preskočeno (wl/prag): {rezultat.preskoceno}")
    print(f"  Greške čitanja      : {rezultat.greske_zapisa}")
    print(f"{'═' * 64}")

    if not rezultat.greske:
        print("  ✓ Nema rodovnih grešaka!")
        return

    # Grupiranje po knjizi
    po_knjizi: dict[str, list[RodovnaGreska]] = {}
    for g in rezultat.greske:
        po_knjizi.setdefault(g.knjiga, []).append(g)

    for knjiga, greske in sorted(po_knjizi.items()):
        print(f"\n  📚 {knjiga}  ({len(greske)} grešaka)")
        for g in greske[:10 if not verbose else 9999]:
            prijedlog_str = f" → {g.prijedlog!r}" if g.prijedlog else " (auto-ispravak nije moguć)"
            print(f"    [{g.score:.1f}] {g.chunk_fajl.name}")
            print(f"      ⚠ {g.opis}")
            print(f"      Original  : {g.original!r}{prijedlog_str}")
            print(f"      Kontekst  : {g.kontekst[:80]}")
        if len(greske) > 10 and not verbose:
            print(f"    ... i još {len(greske)-10} grešaka (--verbose za sve)")

    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroaktivni scanner rodovnih grešaka u Booklyfi/Skriptorij checkpointima."
    )
    parser.add_argument("--scan", action="store_true", help="Samo skeniraj, ne ispravljaj")
    parser.add_argument("--fix", action="store_true", help="Skeniraj i ispravi (regex)")
    parser.add_argument("--ai", action="store_true", help="Uz --fix: koristi AI za teže slučajeve")
    parser.add_argument("--dry-run", action="store_true", help="Prikaži izmjene bez pisanja")
    parser.add_argument("--stats", action="store_true", help="Samo statistika")
    parser.add_argument("--verbose", "-v", action="store_true", help="Sve greške (bez limita prikaza)")
    parser.add_argument("--knjiga", metavar="NAZIV", help="Filtriraj po nazivu knjige")
    parser.add_argument("--prag", type=float, default=11.0, metavar="SCORE",
                        help="Skenira chunkove s ocjenom < PRAG (default: 11 = sve)")
    parser.add_argument("--chk-root", metavar="PUTANJA",
                        help="Override CHECKPOINT_BASE putanje")
    parser.add_argument("--api-key", metavar="KEY", help="Gemini API ključ za --ai mod")
    args = parser.parse_args()

    global CHECKPOINT_BASE
    if args.chk_root:
        CHECKPOINT_BASE = Path(args.chk_root)

    if args.stats:
        rezultat = skeniraj_sve(args.knjiga, args.prag)
        ispisi_izvjestaj(rezultat, args.verbose)
        return

    if not args.scan and not args.fix:
        parser.print_help()
        print("\n⚠ Specificirati --scan ili --fix")
        sys.exit(1)

    # Scan
    rezultat = skeniraj_sve(args.knjiga, args.prag)
    ispisi_izvjestaj(rezultat, args.verbose)

    if not args.fix or not rezultat.greske:
        return

    # Fix
    print(f"\n{'─' * 64}")
    print(f"  Pokretanje ispravki (dry-run={'DA' if args.dry_run else 'NE'}) ...")
    print(f"{'─' * 64}")

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    koristi_ai = args.ai and api_key

    if args.ai and not api_key:
        log.warning("--ai zadan ali nema API ključa (GEMINI_API_KEY env ili --api-key). Koristim samo regex.")

    # Grupiraj greške po fajlu
    po_fajlu: dict[Path, list[RodovnaGreska]] = {}
    for g in rezultat.greske:
        po_fajlu.setdefault(g.chunk_fajl, []).append(g)

    ukupno_izmjena = 0
    for chk_fajl, greske in sorted(po_fajlu.items()):
        log.info(f"Ispravljam: {chk_fajl.name} ({len(greske)} grešaka)")

        # Regex ispravak
        n, _ = ispravi_chunk_regex(chk_fajl, dry_run=args.dry_run)
        ukupno_izmjena += n

        # AI ispravak (za preostale greške ili sve ako --ai)
        if koristi_ai and not args.dry_run:
            n_ai, _ = ispravi_chunk_ai(chk_fajl, api_key, dry_run=False)
            if n_ai > 0:
                log.info(f"  AI: {n_ai} dodatnih ispravki")
                ukupno_izmjena += n_ai
        elif args.dry_run:
            log.info(f"  [DRY-RUN] Preskačem pisanje za: {chk_fajl.name}")

    print(f"\n{'═' * 64}")
    print(f"  Ukupno izmjena: {ukupno_izmjena}")
    print(f"  Backup fajlovi: *.bak_rod_*")
    if args.dry_run:
        print("  ⚠ DRY-RUN — ništa nije zapisano")
    print(f"{'═' * 64}\n")


if __name__ == "__main__":
    main()
