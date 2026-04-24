# ============================================================================
# SKRIPTORIJ V10.1 OMNI-CORE — skriptorij.py
# Ispravljen IndentationError, dodane V10.1 optimizacije
# ============================================================================

import os
import re
import shutil
import zipfile
import time
import json
import asyncio
import random
import requests
import urllib3
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning
from api_fleet import FleetManager

try:
    import mobi
    HAS_MOBI = True
except ImportError:
    HAS_MOBI = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# ============================================================================
# URL GENERATORI
# ============================================================================
def _url_gemini_compat():
    return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def _url_groq():
    return "https://api.groq.com/openai/v1/chat/completions"


def _url_samba():
    return "https://api.sambanova.ai/v1/chat/completions"


def _url_cerebras():
    return "https://api.cerebras.ai/v1/chat/completions"


def _url_mistral():
    return "https://api.mistral.ai/v1/chat/completions"


def _url_cohere():
    return "https://api.cohere.com/v2/chat"


def _url_openrouter():
    return "https://openrouter.ai/api/v1/chat/completions"


def _url_github():
    return "https://models.inference.ai.azure.com/chat/completions"


def _url_together():
    return "https://api.together.xyz/v1/chat/completions"


def _url_fireworks():
    return "https://api.fireworks.ai/inference/v1/chat/completions"


def _url_chutes():
    return "https://llm.chutes.ai/v1/chat/completions"


def _url_huggingface():
    return "https://router.huggingface.co/v1/chat/completions"


def _url_kluster():
    return "https://api.kluster.ai/v1/chat/completions"


def _url_gemma():
    return "https://api.together.xyz/v1/chat/completions"


def _url_daisy():
    return "http://www.daisy.org/z3986/2005/ncx/"


# ============================================================================
# GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita
# ============================================================================
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}


def _get_provider_lock(prov: str):
    if prov not in _PROVIDER_LOCKS:
        _PROVIDER_LOCKS[prov] = None
    return prov


_PROVIDER_MIN_GAP = {
    "GEMINI": 8.0,
    "GROQ": 6.0,
    "CEREBRAS": 2.0,
    "SAMBANOVA": 2.5,
    "MISTRAL": 3.0,
    "COHERE": 3.0,
    "OPENROUTER": 3.0,
    "GITHUB": 6.0,
    "TOGETHER": 3.0,
    "FIREWORKS": 3.0,
    "CHUTES": 3.0,
    "HUGGINGFACE": 4.0,
    "KLUSTER": 4.0,
    "GEMMA": 5.0,
}
MIN_GAP = 2.5

_RPM_THROTTLE_MULTIPLIER = 1.8
_JITTER_MIN = 0.3
_JITTER_MAX = 1.2


async def _ensure_provider_lock(prov: str) -> asyncio.Lock:
    """Vrati per-provider asyncio.Lock, kreira novi ako je vezan za pogrešan loop."""
    import asyncio
    lock = _PROVIDER_LOCKS.get(prov)
    if lock is None:
        lock = asyncio.Lock()
        _PROVIDER_LOCKS[prov] = lock
    else:
        try:
            # Proveri da li je lock vezan za trenutni event loop
            loop = asyncio.get_running_loop()
            # Ako lock ima _loop atribut i razlikuje se, kreiraj novi
            if hasattr(lock, "_loop") and lock._loop is not loop:
                lock = asyncio.Lock()
                _PROVIDER_LOCKS[prov] = lock
        except RuntimeError:
            # Nema running loop, kreiraj novi
            lock = asyncio.Lock()
            _PROVIDER_LOCKS[prov] = lock
    return lock


async def _ensure_global_lock():
    return await _ensure_provider_lock("__global__")


def _safe_get_model(fleet, prov_upper, default=None):
    try:
        return fleet.get_active_model(prov_upper)
    except (AttributeError, KeyError):
        return (
            default
            if default is not None
            else ("gemini-2.5-flash" if prov_upper == "GEMINI" else None)
        )


def _get_key_state(fleet, prov_upper: str, key: str):
    try:
        keys_list = fleet.fleet.get(prov_upper, [])
        if isinstance(keys_list, list):
            for ks in keys_list:
                if getattr(ks, "key", None) == key:
                    return ks
            return None
        if isinstance(keys_list, dict):
            raw = keys_list.get(key)
            if raw is None:
                return None

            class _FakeKS:
                pass

            fks = _FakeKS()
            for k, v in raw.items() if isinstance(raw, dict) else {}:
                setattr(fks, k, v)
            return fks
    except Exception:
        pass
    return None


# ============================================================================
# #15: AI MARKER ČIŠĆENJE
# ============================================================================
_AI_TELLS_PATTERNS = [
    r"\bNaravno[,!]?\b",
    r"\bSvakako[,!]?\b",
    r"\bKao što znate\b",
    r"\bZanimljivo je da\b",
    r"\bVrijedi napomenuti\b",
    r"\bU zaključku\b",
    r"\bSažeto rečeno[,]?\b",
    r"\bUkratko[,]?\b",
    r"Evo (?:rezultata|prijevoda|teksta)[:\.]?",
    r"Izvolite[:\.]?",
    r"Prijevod[:\.]?",
    r"Lektura[:\.]?",
    r"Ovdje je (?:vaš|tvoj) (?:tekst|prijevod)[:\.]?",
    r"Nadam se da (?:vam|ti) (?:se sviđa|je korisno)[!.]?",
    r"Rado (?:sam|ću) (?:pomoći|prevesti)[!.]?",
]

_PLACEHOLDER_STRINGS = frozenset(
    {
        "lektorisani tekst ovdje",
        "korigirani tekst ovdje",
        "<ovdje_idi_lektorirani_tekst>",
        "<ovdje_idi_korigirani_tekst>",
        "ovdje_idi_lektorirani_tekst",
        "ovdje_idi_korigirani_tekst",
        "tekst ovdje",
        "vaš tekst ovdje",
    }
)


def _je_placeholder(tekst: str) -> bool:
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    return cist in _PLACEHOLDER_STRINGS


def _ocisti_ai_markere(tekst: str) -> str:
    for p in _AI_TELLS_PATTERNS:
        tekst = re.sub(p, "", tekst, flags=re.IGNORECASE)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


# ============================================================================
# V10.1: PAMETNI JSON PARSING
# ============================================================================
_QUOTE_CHARS = r'["\u201c\u201d\u201e\u2018\u2019]'
_JSON_OMOTAC_RE = re.compile(
    r"^\s*\{\s*"
    + _QUOTE_CHARS
    + r"?[\w_]+"
    + _QUOTE_CHARS
    + r"?\s*:\s*"
    + _QUOTE_CHARS
    + r"([\s\S]*?)"
    + _QUOTE_CHARS
    + r"?\s*\}\s*$",
    re.DOTALL,
)


def _cisti_json_wrapper(tekst: str) -> str:
    if not tekst:
        return tekst
    stripped = tekst.strip()
    if not stripped.startswith("{"):
        return tekst
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and obj:
            val = (
                obj.get("finalno_polirano")
                or obj.get("korektura")
                or obj.get("tekst")
                or next(iter(obj.values()), "")
            )
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        pass
    m = _JSON_OMOTAC_RE.match(stripped)
    if m:
        extracted = m.group(1).strip()
        if extracted:
            return extracted
    return tekst


def _smart_extract(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in ["finalno_polirano", "korektura", "tekst", "translation", "polished_text"]:
                if key in data and data[key] and isinstance(data[key], str):
                    val = str(data[key]).strip()
                    if len(val) > 10:
                        return val
            for v in data.values():
                if isinstance(v, str) and len(v.strip()) > 10:
                    return v.strip()
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{\s*"finalno_polirano"\s*:\s*"([^"]+)"\s*\}', raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'\{\s*"korektura"\s*:\s*"([^"]+)"\s*\}', raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return _agresivno_cisti(raw)


# ============================================================================
# DETEKCIJA ENGLESKOG
# ============================================================================
_EN_STOPWORDS = frozenset(
    {
        "the", "and", "was", "for", "are", "with", "his", "they", "have", "from",
        "this", "that", "will", "what", "their", "said", "been", "which", "into",
        "but", "not", "she", "her", "had", "him", "its", "our", "out", "who",
        "when", "than", "then", "some", "very", "just", "like", "your", "can",
        "by", "of", "in", "is", "it", "he", "we", "at", "an", "to", "be", "as",
        "or", "do", "if", "no", "my", "us", "am", "go", "up", "so", "me", "on",
        "oh", "all", "one", "has", "any", "new", "now", "how", "old", "did",
        "say", "get", "let", "two", "see", "too", "try", "may", "own", "way",
        "day", "man", "big", "got", "set", "few", "off", "yes", "yet", "ago",
        "far", "add", "age", "air", "bad", "bed", "bit", "box", "boy", "car",
        "cut", "end", "eye", "fit", "fun", "god", "guy", "hit", "hot", "job",
        "key", "kid", "law", "leg", "lot", "low", "mad", "mom", "men", "net",
        "odd", "oil", "pay", "run", "sad", "sit", "six", "sky", "son", "sun",
        "ten", "top", "toy", "war", "win", "won", "arm", "ask", "act", "also",
        "away", "back", "came", "come", "days", "does", "each", "even", "ever",
        "eyes", "face", "feel", "find", "gave", "give", "goes", "good", "hand",
        "here", "home", "keep", "know", "last", "left", "life", "live", "123",
        "long", "look", "made", "make", "mind", "more", "much", "must", "need",
        "next", "once", "only", "open", "over", "part", "real", "room", "same",
        "seem", "show", "side", "take", "tell", "them", "time", "told", "took",
        "turn", "used", "want", "went", "well", "work", "year", "down", "help",
        "high", "hold", "knew", "name", "upon", "were", "most", "both", "many",
        "such", "thus", "after", "before", "while", "those", "these", "every",
        "could", "would", "should", "about", "there", "still", "under", "again",
        "right", "other", "place", "think", "three", "voice", "wrote", "years",
        "hands", "night", "light", "small", "world", "found", "never", "first",
        "great", "large", "later", "asked", "being", "stand", "heard", "thing",
        "going", "whole", "young", "given", "point", "taken", "until", "might",
        "along", "begin", "below", "bring", "built", "called", "cause", "close",
        "shall", "since", "today", "value", "words", "write", "through",
        "published", "library", "division", "copyright", "reserved", "rights",
        "author", "edition", "chapter", "volume", "series", "press", "books",
        "fiction", "novel", "story", "tales", "written", "edited", "cover",
    }
)

_HR_DIACRITICALS = frozenset("šćčžđŠĆČŽĐ")


def _detektuj_en_ostatke(tekst: str) -> float:
    try:
        cist = re.sub(r"<[^>]+>", "", tekst).lower()
        if any(c in _HR_DIACRITICALS for c in cist):
            return 0.0
        words = re.findall(r"\b[a-z]{2,}\b", cist)
        if not words:
            return 0.0
        return sum(1 for w in words if w in _EN_STOPWORDS) / len(words)
    except Exception:
        return 0.0


# ============================================================================
# #16 + #21: POBOLJŠANA HALUCINACIJA DETEKCIJA
# ============================================================================
def _detektuj_halucinaciju(original: str, prijevod: str, uloga: str = "LEKTOR") -> bool:
    try:
        orig_len = len(re.sub(r"<[^>]+>", "", original).strip())
        prev_len = len(re.sub(r"<[^>]+>", "", prijevod).strip())
        if orig_len == 0 or prev_len < 15:
            return False
        ratio = prev_len / orig_len

        if uloga == "LEKTOR":
            if ratio < 0.92 or ratio > 1.12:
                return True
        else:
            if ratio < 0.15 or ratio > 3.0:
                return True

        recenice = [
            s.strip() for s in re.split(r"[.!?]", prijevod) if len(s.strip()) > 15
        ]
        if any(v >= 4 for v in Counter(recenice).values()):
            return True
        return False
    except Exception:
        return False


def _agresivno_cisti(tekst: str) -> str:
    if not tekst:
        return ""
    tekst = _cisti_json_wrapper(tekst)
    patterns = [
        r"https?://googleusercontent\.com/immersive_entry_chip/\d+",
        r"```(?:html|json|text|xml)?\s*",
        r"```\s*$",
        r"ZADATAK:.*?\n",
        r"GLOSAR:.*?\n",
        r"SYSTEM:.*?\n",
        r"\*\*(.*?)\*\*",
        r'^\s*\{["\u201c\u201d\u201e]?[\w_]+["\u201c\u201d\u201e]?\s*:\s*["\u201c\u201d\u201e]([\s\S]*?)["\u201c\u201d\u201e]\s*\}\s*$',
        r"<OVDJE_IDI_[A-Z_]+>",
    ]
    for p in patterns:
        tekst = re.sub(
            p,
            r"\1" if r"\1" in p else "",
            tekst,
            flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
        )
    return _ocisti_ai_markere(tekst.strip())


# ============================================================================
# #26: DETEKCIJA TIPA BLOKA (za adaptive temperature)
# ============================================================================
_DIALOG_RE = re.compile(r"[—\-" "„].*?[.!?]", re.DOTALL)
_POETSKI_INDIKATORI = re.compile(
    r"(srce|duša|tišina|sjaj|suza|vjetar|svjetlost|tamno|san|čežnja|bol|ljubav|nada)",
    re.IGNORECASE,
)


def _detektuj_tip_bloka(tekst: str) -> str:
    cist = re.sub(r"<[^>]+>", "", tekst)
    dijalog_znakovi = len(_DIALOG_RE.findall(cist))
    ukupne_recenice = max(1, len(re.findall(r"[.!?]", cist)))
    dijalog_ratio = dijalog_znakovi / ukupne_recenice

    if dijalog_ratio > 0.35:
        return "dijalog"
    if len(_POETSKI_INDIKATORI.findall(cist)) >= 3 and ukupne_recenice < 8:
        return "poetski"
    return "naracija"


def _adaptive_temp(uloga: str, tip_bloka: str, bazna_temp: float) -> float:
    if uloga in ("LEKTOR", "GUARDIAN"):
        if tip_bloka == "dijalog":
            return min(bazna_temp + 0.15, 0.72)
        elif tip_bloka == "poetski":
            return min(bazna_temp + 0.25, 0.82)
        else:
            return bazna_temp
    elif uloga == "POLISH":
        if tip_bloka == "poetski":
            return 0.85
        elif tip_bloka == "dijalog":
            return 0.75
        else:
            return 0.68
    elif uloga == "KOREKTOR":
        return 0.22
    return bazna_temp


# ============================================================================
# #27: QUALITY SCORING (ISPRAVLJEN POTPIS)
# ============================================================================
_QUALITY_SCORER_SYS = """\
Ti si kvalitetni sudac književnog prijevoda na bosanski/hrvatski jezik.
Ocijeni dati tekst na skali 1-10 prema sljedećim kriterijima:
- 9-10: Print-ready, nulta kalkiranja, savršena gramatika, živ stil
- 7-8: Jako dobro, minimalni tragovi mašinskog prijevoda
- 5-6: Prihvatljivo, ali vidljiva kalkiranja ili stilske slabosti
- 3-4: Loše, puno engleizama i kalkiranja
- 1-2: Katastrofalno, uglavnom engleski ili besmislice

Vrati ISKLJUČIVO JSON: {"ocjena": <broj 1-10>, "razlog": "<kratko>"}
"""

_QUALITY_RESCUE_THRESHOLD = 6.5


async def _scoruj_kvalitetu(
    tekst: str, engine_fn, chunk_idx: int, file_name: str, self_obj=None
) -> float:
    try:
        cist = BeautifulSoup(tekst, "html.parser").get_text()[:600]
        if self_obj is not None:
            raw, _ = await self_obj._call_ai_engine(
                f"Ocijeni ovaj tekst:\n{cist}",
                chunk_idx,
                uloga="SCORER",
                filename=file_name,
            )
        else:
            raw, _ = await engine_fn(
                f"Ocijeni ovaj tekst:\n{cist}",
                chunk_idx,
                uloga="SCORER",
                filename=file_name,
            )
        if raw:
            m = re.search(r"\{.*?\}", raw, re.DOTALL)
            if m:
                obj = json.loads(m.group())
                return float(obj.get("ocjena", 8.0))
    except Exception:
        pass
    return 8.0
# ============================================================================
# LOGIRANJE
# ============================================================================
audit_logs = []


def add_audit(msg, atype="info", en_text="", shared_stats=None):
    global audit_logs
    ts = datetime.now().strftime("%H:%M:%S")
    style_map = {
        "system": (
            "border-left:4px solid #c026d3",
            "background:#2e0b36",
            "color:#f0abfc",
        ),
        "tech": (
            "border-left:3px solid #cbd5e1",
            "background:#1e293b",
            "color:#94a3b8; font-size:0.85em",
        ),
        "warning": ("border-left:3px solid #fa0", "background:#331100", "color:#fa0"),
        "error": ("border-left:4px solid #f44", "background:#300", "color:#f44"),
        "validator": (
            "border-left:3px solid #10b981",
            "background:#052e16",
            "color:#6ee7b7; font-size:0.85em",
        ),
        "quality": (
            "border-left:3px solid #f59e0b",
            "background:#1c1400",
            "color:#fcd34d; font-size:0.85em",
        ),
    }
    if atype == "accordion":
        entry = f"<div>{en_text}</div>"
    else:
        s = style_map.get(
            atype,
            (
                "border-left:2px solid #334155",
                "background:transparent",
                "color:#94a3b8; font-size:0.9em",
            ),
        )
        entry = (
            f"<div style='{s[0]}; {s[1]}; {s[2]}; padding:8px; margin-bottom:5px; border-radius:4px;'>"
            f"<b>[{ts}]</b> {msg}{('<br>' + en_text) if en_text else ''}</div>"
        )
    audit_logs.append(entry)
    if len(audit_logs) > 300:
        audit_logs.pop(0)
    if shared_stats is not None:
        shared_stats["live_audit"] = "".join(audit_logs)


# ============================================================================
# TIPOGRAFSKA OBRADA + AUTOMATSKA GRAMATIČKA KOREKCIJA (bez AI poziva)
# ============================================================================
_KALKIRANJE_REGEX = [
    (
        r"\b(mogao|mogla|moglo|mogli|mogle|uspio|uspjela|uspjelo|uspjeli|"
        r"pokušao|pokušala|počeo|počela|htio|htjela|morao|morala)\s+je\s+da\s+(\w+)",
        lambda m: m.group(1) + " je " + m.group(2) + "ti"
        if not m.group(2).endswith("ti")
        else m.group(0),
    ),
    (r"\bbio\s+je\s+u\s+stanju\s+da\b", "mogao je"),
    (r"\bbila\s+je\s+u\s+stanju\s+da\b", "mogla je"),
    (r"\bnije\s+bio\s+u\s+mogu[cć]nosti\b", "nije mogao"),
    (r"\bnije\s+bila\s+u\s+mogu[cć]nosti\b", "nije mogla"),
    (r"\bu\s+pogledu\s+toga\b", "što se toga tiče"),
    (r"\bna\s+kraju\s+krajeva\b", "naposljetku"),
    (r"\bčinjenica\s+je\s+da\s+", ""),
    (r"  +", " "),
    (r" ([,;:!?])", r"\1"),
    (r"\.\.\.", "…"),
]


def _automatska_korekcija(tekst: str) -> str:
    for pattern, replacement in _KALKIRANJE_REGEX:
        try:
            if callable(replacement):
                tekst = re.sub(
                    pattern, replacement, tekst, flags=re.IGNORECASE | re.UNICODE
                )
            else:
                tekst = re.sub(
                    pattern, replacement, tekst, flags=re.IGNORECASE | re.UNICODE
                )
        except Exception:
            pass
    return tekst


def _post_process_tipografija(tekst: str) -> str:
    tekst = re.sub(r"\.\.\.", "…", tekst)
    tekst = re.sub(r"\.{4,}", "…", tekst)
    tekst = re.sub(r"(<p[^>]*>)\s*-\s", r"\1— ", tekst)
    tekst = re.sub(r"(<p[^>]*>)\s*–\s", r"\1— ", tekst)

    def _fix_spaces(m: re.Match) -> str:
        return re.sub(r"  +", " ", m.group())

    tekst = re.sub(r"(?<=>)([^<]+)(?=<)", _fix_spaces, tekst)
    tekst = re.sub(r"^([^<]+)", _fix_spaces, tekst)
    tekst = re.sub(r"([^>]+)$", _fix_spaces, tekst)

    def _fix_navodnici(m: re.Match) -> str:
        return re.sub(r'"([^"]+)"', "\u201e\\1\u201c", m.group())

    tekst = re.sub(r"(?<=>)([^<]+)(?=<)", _fix_navodnici, tekst)
    tekst = re.sub(r"^([^<]+)", _fix_navodnici, tekst)
    tekst = re.sub(r"([^>]+)$", _fix_navodnici, tekst)
    tekst = re.sub(r"\s+([,;:!?])", r"\1", tekst)
    return tekst


# ============================================================================
# #21 + #22: ZATEGNUTI SYSTEM PROMPTI + DINAMIČKI STILSKI VODIČ
# ============================================================================
_PREVODILAC_TEMPLATE = """Ti si vrhunski književni prevodilac-lektor s 25 godina iskustva u vodećim izdavačkim kućama (Fraktura, VBZ, Ljevak). Radiš JEDAN prolaz koji istovremeno prevodi i lektorira do print-ready standarda.

KONTEKST: {ton_injekcija}
GLOSAR (strogo koristi): {glosar_injekcija}
PRETHODNI ODLOMAK (nastavi istim stilom/POV-om): {prev_kraj}

ZADATAK: Prevedi engleski tekst direktno u finalni bosanski/hrvatski.
Radi sve u jednom prolazu — prevođenje + lektura zajedno.

PRAVILA (sva obavezna):

1. PRIJEVOD — svaka rečenica, nijansa i emocija mora biti prenesena.
   Idiomi: ekvivalenti (ne doslovno) — "kick the bucket"→"ispustiti dušu",
   "it's raining cats and dogs"→"pada kao iz kabla", "break a leg"→"sretno"

2. LEKTURA — eliminiraj kalkiranja odmah:
   "bio je u stanju da"→"mogao je" | "uspio je da uradi"→"uspio je uraditi"
   "nije bio u mogućnosti"→"nije mogao" | pasiv→aktiv gdje zvuči bolje
   Varij dijalog: reče/odvrati/promrmlja/upita/šapnu/dobaci

   PRIMJERI DOBROG I LOŠEG:
   LOŠE: "Bio je u stanju da vidi kuću." → DOBRO: "Ugledao je kuću."
   LOŠE: "Rekao je tiho." → DOBRO: "Prošaptao je."
   LOŠE: "Hodao je sporo." → DOBRO: "Vukao se."

3. KNJIŽEVNI STIL:
   Ritam: izmjenjuj kratke i duge rečenice
   Epiteti: "rekao tiho"→"prošaptao" | "hodao sporo"→"vukao se"
   Vokabular: bogat, raznovrstan — nikad ista oznaka dva puta u odlomku

4. GRAMATIKA:
   Futur: "radit ću" | Kondicional: "radio bih"
   Zarezi ispred: koji/koja/koje/što/jer/da
   Navodnici: „ovako" | Dijalog: — em-crtica | Tri tačke: … (U+2026)

5. HTML: Zadrži SVE tagove tačno (<p>, <em>, <i>, <b>, <br>)

IZLAZ: SAMO finalni tekst. Nula komentara. Nula uvoda. Nula JSON omotača.
"""

_LEKTOR_TEMPLATE = """\
Ti si Glavni urednik u elitnoj izdavačkoj kući (nivo Fraktura / VBZ / Ljevak).
Tvoj zadatak je pretvoriti sirovi mašinski prijevod u profesionalni književni tekst koji je ravan konačnom printanom primjerku.

KONTEKST KNJIGE: {knjiga_kontekst}

STILSKI VODIČ KNJIGE (OBAVEZNO POŠTOVATI DO ZADNJEG DETALJA):
{stilski_vodic}

GLOSAR LIKOVA I TERMINA (NE MIJENJAJ NIKAD):
{glosar_injekcija}

KONTINUITET — PRETHODNI ODLOMAK: "{prev_kraj}"
KONTEKST POGLAVLJA: {chapter_summary}
Nastavi identičnim glagolskim vremenom, POV-om i stilom.

IMPERATIVNA PRAVILA — SVA MORAJU BITI ISPUNJENA:

PRAVILO 1 — APSOLUTNA VJERNOST SADRŽAJU
- Svaka informacija, nijansa i emocija iz sirovog prijevoda mora biti sačuvana.
- Zabranjeno je dodavati, izbacivati ili mijenjati bilo koji element sadržaja.

PRAVILO 2 — ELIMINACIJA MAŠINSKIH KALKIRANJA (PRIORITET!)
Obavezno prepoznaj i ispravi SVE od sljedećeg:
  "bio je u stanju da" -> "mogao je"
  "nije bio u mogućnosti" -> "nije mogao"
  "uspio je da uradi" -> "uspio je uraditi"
  "pokušao je da" -> "pokušao je + infinitiv"
  "činjenica je da" -> obrisi frazu, nastavi direktno
  "u pogledu toga" -> "što se toga tiče"
  "na kraju krajeva" -> "naposljetku / konačno"
  Imeničke konstrukcije engl. tipa: "odluka je bila napraviti" -> "odlučio je"
  Pasiv gdje aktiv zvuči prirodnije -> ispravi u aktiv
  Doslovni prijevodi idioma -> zamijeni B/H/S ekvivalentom
  Pogrešan red riječi (kopija engleskog reda) -> preuredi po B/H/S logici
  "rekao je" svaki put -> varij: "reče", "odvrati", "promrmlja", "upita", "uzviknu", "dobaci"

PRIMJERI DOBROG I LOŠEG (OBRATI PAŽNJU):
  LOŠE: "Bio je u stanju da vidi kuću na horizontu."
  DOBRO: "Ugledao je kuću na horizontu."
  
  LOŠE: "Rekao je tiho, jedva čujno."
  DOBRO: "Prošaptao je."
  
  LOŠE: "Hodao je sporo kroz šumu."
  DOBRO: "Vukao se kroz šumu."

PRAVILO 3 — KNJIŽEVNI STIL PRINT-READY KVALITETE
- Vokabular: bogat, precizan, raznovrstan — nikad ista oznaka dva puta u istom odlomku.
- Ritam: svjesno izmjenjuj kratke i duge rečenice (kao u štampanom romanu).
- Epiteti: ne dozvoli generičnost — "rekao je tiho" -> "prošaptao je"; "hodao je sporo" -> "vukao se".
- Emocionalni naboj identičan originalu — ne smanji, ne pojačaj.

PRAVILO 4 — GRAMATIKA I PRAVOPIS B/H/S STANDARDA
- Futur I: "radit ću" (književni stil), "ću raditi" samo za naglasak
- Kondicional I: "radio bih" (ne "bi radio" osim za naglasak)
- Glagolski vid: dosljedno kroz cijeli odlomak (svršeni/nesvršeni)
- Zarezi OBAVEZNO ispred: koji/koja/koje/što/jer/da (zavisna surečenica)
- Zarezi NE ispred "i" osim kod nabrajanja triju i više članova
- Navodnici: „ovako" (otvara niski „, zatvara visoki ")
- Em-crtica (—) za dijalog, tri tačke: … (jedan Unicode znak U+2026)
- Nikad razmak ispred interpunkcijskog znaka

PRAVILO 5 — DIJALOG
- Svaka replika počinje em-crticom: — Ovako.
- Atribucija replika: ne ponavlja isti glagol više od jednom po odlomku.
- Unutarnji monolog/misli: <em>kurzivom ovako</em>
- Dijalog zvuči živo i spontano.

PRAVILO 6 — HTML TAGOVI
- Zadrži SVE HTML tagove tačno kakvi su (<p>, <em>, <i>, <b>, <br>, <div>, itd.)
- Ne dodaj, ne uklanjaj, ne mijenjaj tagove ni strukturu paragrafa.

PRAVILO 7 — ČISTOĆA IZLAZA
- Vrati ISKLJUČIVO JSON. Apsolutno nula komentara, uvoda, napomena.
- Ako tekst nije mogao biti poboljšan, vrati ga nepromijenjenog (ali u JSON-u).

Vrati ISKLJUČIVO JSON: {{"finalno_polirano": "LEKTORIRANI_TEKST_OVDJE"}}
"""

_KOREKTOR_TEMPLATE = """\
Ti si vrhunski korektor koji priprema rukopis za tisak u najvećim izdavačkim kućama.
Tekst je već lektoriran — tvoj zadatak je isključivo tehnička i gramatička savršenost.

PROVJERI I ISPRAVI SVAKU KATEGORIJU:

1. PADEŽI I SLAGANJE
   - Sklonidba imenica u svim padežima (gen., dat., akuz., lok., instr.)
   - Slaganje pridjeva s imenicom u rodu, broju i padežu
   - Glagolsko slaganje s imeničkom skupinom

2. GLAGOLSKA VREMENA I VIDOVI
   - Futur I: "radit ću"; kondicional I: "radio bih"
   - Glagolski vidovi: svršeni/nesvršeni — dosljednost kroz odlomak
   - GREŠKA: modalni glagol + "da" + prezent -> modal + infinitiv
     Primjeri: "uspio je da uradi" -> "uspio je uraditi"; "pokušao je da kaže" -> "pokušao je kazati"

3. INTERPUNKCIJA
   - Zarez OBAVEZNO ispred: koji/koja/koje/što/jer/da (zavisna surečenica)
   - Zarez NE ispred "i" između dviju surečenica (osim nabrajanja 3+)
   - Em-crtica (—) za dijalog i stanku; en-crtica (–) za raspon (str. 10–15)
   - Tri tačke: mora biti … (jedan Unicode znak U+2026, nikad "...")
   - Nikad razmak ISPRED znaka interpunkcije
   - Nikad dvostruki razmaci

4. NAVODNICI
   - Otvaranje: „ (U+201E — na dnu), zatvaranje: " (U+201C — gore lijevo)
   - Ugniježđeni navodnici: ‚unutarnji' (U+201A i U+2018)

5. KONZISTENTNOST
   - Imena likova i termini: identični kroz cijeli tekst
   - Titule i forme obraćanja: dosljedne

Vrati ISKLJUČIVO JSON: {{"korektura": "KORIGIRANI_TEKST_OVDJE"}}
"""

_VALIDATOR_SYS = """\
Ti si stručni kontrolor kvalitete prijevoda s engleskog na bosanski/hrvatski.
Provjeri da li prijevod vjerno prenosi SMISAO originalnog engleskog teksta.

Gledaj ISKLJUČIVO:
1. Semantičku vjernost — jesu li sve informacije prenesene
2. Nijanse i emocionalni ton — nije prenaglašeno, nije umanjeno
3. Imena i termini — konzistentno prevedeni/zadržani

NE gledaj: stil, gramatiku, interpunkciju (to radi lektor/korektor).

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

_POST_LEKTOR_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete lekture. Provjeri je li lektura POGORŠALA ili IZGUBILA sadržaj.

ODBIJI lekturu (ok=false) ako:
1. Nedostaje rečenica ili dio sadržaja koji postoji u prijevodu
2. Dodan je sadržaj koji NE postoji u prijevodu
3. Promijenjeno je ime lika ili ključni termin
4. Tekst je na engleskom ili sadrži >5% engleskih riječi
5. Lektura je gotovo identična prijevodu (nije ništa popravila, a prijevod ima očigledna kalkiranja)

PRIHVATI lekturu (ok=true) ako:
- Sav sadržaj je sačuvan, samo je stil/gramatika poboljšana
- Manje promjene dužine (±15%) su normalne za kvalitetnu lekturu
- Idiomi i kalkiranja su ispravno zamijenjeni prirodnim B/H/S izrazima

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

_POST_POLISH_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete završne obrade (polish). Provjeri je li polish korak POGORŠAO tekst.

ODBIJI polish (ok=false) ako:
1. Tekst je skraćen za >20% bez sadržajnog razloga
2. Dodan je sadržaj koji ne postoji u prethođenom tekstu
3. Promijenjeno je ime lika ili ključni termin
4. Tekst sadrži engleske fraze kojih ranije nije bilo
5. Tekst zvuči kao da je prepisan na drugi žanr ili ton

PRIHVATI (ok=true) ako:
- Stil je polifiran, sadržaj nepromijenjen
- Manje stilske intervencije (burstiness, ritam) su u redu

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "<kratko>"}
"""

_ANALIZA_SYS = """\
Pročitaj uvodni tekst knjige i ekstraktuj detaljan stilski profil koji će voditi lektora kroz cijelu knjigu.

Vrati ISKLJUČIVO JSON:
{
  "zanr": "...",
  "ton": "...",
  "stil_pripovijedanja": "...",
  "period": "...",
  "likovi": {"ImeLika": "opis, M/Ž, kako govori"},
  "glosar": {"OrigTerm": "kako prevesti na B/H/S"},
  "stilski_vodic": "Detaljan opis (5-8 rečenica) književnog stila ove konkretne knjige: (a) tipična dužina i ritam rečenica, (b) vokabular — jednostavan/složen/arhaičan/kolokvijalan, (c) kako se opisuju emocije — direktno/indirektno/kroz radnje, (d) karakteristike dijaloga — formalni/neformalni/regionalni, (e) pripovijedni glas i distanca prema likovima, (f) tri konkretna B/H/S književna ekvivalenta tipičnih engleskih fraza iz ovog teksta."
}"""

_CHAPTER_SUMMARY_SYS = """\
Ti si književni asistent. Napiši kratki sažetak (2-4 rečenice) ovog poglavlja na bosanskom/hrvatskom jeziku.
Fokusiraj se na: ključne događaje, razvoj likova, promjene tona ili mjesta radnje.
Sažetak će se koristiti kao kontekst za sljedeće poglavlje.
Vrati ISKLJUČIVO sažetak kao obični tekst, bez JSON-a, bez komentara.
"""

_GLOSAR_UPDATE_SYS = """\
Ti si književni analitičar. Analiziran je novi dio knjige.
Identificiraj NOVE likove, termini ili fraze koji nisu u postojećem glosaru.
Vrati ISKLJUČIVO JSON s novim unosima (ne ponavljaj postojeće):
{
  "novi_likovi": {"ImeLika": "opis, M/Ž, kako govori"},
  "novi_termini": {"OrigTerm": "kako prevesti na B/H/S"}
}
"""

_GUARDIAN_SYS = """\
Ti si Consistency Guardian — strogi kontrolor konzistentnosti cijele knjige.
Provjeri i ispravi samo ako je potrebno: imena likova, opisi, glasovi, glagolska vremena, ključni termini, logičke nelogičnosti.
Posebno pazi na: POV konzistentnost, glagolska vremena unutar odlomka, ponavljanja iste fraze u blizini.
Vrati ISKLJUČIVO ispravljeni tekst. Bez komentara."""

_POLISH_TEMPLATE = """\
Ti si vrhunski human-like polisher sa 25+ godina iskustva u izdavaštvu.
Uzmi ovaj tekst i pretvori ga u konačnu, print-ready verziju koja zvuči 100% ljudski.
Koristi burstiness, perplexity, prirodne nepravilnosti i suptilne ljudske dodire.
Žanr: {zanr} | Ton: {ton} | Tip bloka: {tip_bloka}
Stilski vodič: {stilski_vodic}
Vrati SAMO polirani tekst. Nula komentara."""

_SCORER_SYS = _QUALITY_SCORER_SYS


# ============================================================================
# EPUB TIPOGRAFIJA — POMOĆNE FUNKCIJE
# ============================================================================
def _to_roman(n: int) -> str:
    if n < 1:
        return str(n)
    vals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result = ""
    for v, s in vals:
        while n >= v:
            result += s
            n -= v
    return result


_EPUB_PAPER_CSS = (
    "body {"
    "  background-color: #f4ede0 !important;"
    "  background-image:"
    "    repeating-linear-gradient("
    "      0deg, transparent, transparent 97%, rgba(139,90,43,0.07) 100%),"
    "    repeating-linear-gradient("
    "      90deg, transparent, transparent 98%, rgba(139,90,43,0.04) 100%),"
    "    radial-gradient(ellipse at 18% 18%, rgba(180,140,90,0.15) 0%, transparent 52%),"
    "    radial-gradient(ellipse at 82% 82%, rgba(160,110,60,0.12) 0%, transparent 48%),"
    "    radial-gradient(ellipse at 50% 50%,"
    "      rgba(245,230,205,0) 38%, rgba(180,130,70,0.08) 100%)"
    "    !important;"
    "  background-size: 100% 24px, 24px 100%, 100% 100%, 100% 100%, 100% 100% !important;"
    "  background-attachment: fixed !important;"
    "  color: #1a1008 !important;"
    "  font-family: 'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif !important;"
    "  font-size: 1em !important;"
    "}"
    "p {"
    "  line-height: 1.85 !important;"
    "  text-indent: 1.8em !important;"
    "  margin-bottom: 0.75em !important;"
    "  font-size: 1.05em !important;"
    "  text-align: justify !important;"
    "  font-family: 'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif !important;"
    "}"
    "span, em, i, b, strong, cite, abbr {"
    "  font-size: inherit !important;"
    "  font-family: inherit !important;"
    "}"
)


def _inject_epub_global_css(soup) -> None:
    head = soup.find("head")
    if head is None:
        html_tag = soup.find("html")
        if html_tag:
            head = soup.new_tag("head")
            html_tag.insert(0, head)
    if head is not None:
        style_tag = soup.new_tag("style")
        style_tag.string = _EPUB_PAPER_CSS
        head.append(style_tag)


def _zamijeni_epub_css(html_fajlovi: list, work_dir, log_fn=None) -> int:
    work_dir_resolved = Path(work_dir).resolve()
    zamijenjeni: set = set()
    for fajl in html_fajlovi:
        try:
            parser = (
                "xml" if fajl.suffix.lower() in {".xhtml", ".xml"} else "html.parser"
            )
            soup = BeautifulSoup(fajl.read_text("utf-8", errors="ignore"), parser)
            for link in soup.find_all("link"):
                rel = link.get("rel", [])
                if isinstance(rel, str):
                    rel = rel.split()
                if "stylesheet" not in rel:
                    continue
                href = link.get("href", "")
                if not href or not href.lower().endswith(".css"):
                    continue
                css_path = (fajl.parent / href).resolve()
                try:
                    css_path.relative_to(work_dir_resolved)
                except ValueError:
                    continue
                if css_path in zamijenjeni:
                    continue
                if css_path.exists():
                    css_path.write_text(_EPUB_PAPER_CSS, encoding="utf-8")
                    zamijenjeni.add(css_path)
        except Exception:
            continue
    if zamijenjeni and log_fn:
        log_fn(f"🎨 EPUB CSS zamijenjen u {len(zamijenjeni)} fajl(ov)a.", "tech")
    return len(zamijenjeni)


# ============================================================================
# EPUB PRE-PROCESSING
# ============================================================================
_ROMAN_NUMERAL_RE = re.compile(
    r"(?<![A-Za-z])(?=[MDCLXVI])(?:M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))(?![A-Za-z])",
)


def _ocisti_epub_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(True):
            for node in list(tag.children):
                if isinstance(node, NavigableString):
                    cleaned = re.sub(r"^[\n\r\t\v]+", "", str(node))
                    if cleaned != str(node):
                        node.replace_with(NavigableString(cleaned))

            if tag.name in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
                t = tag.get_text(strip=True)
                m = _ROMAN_NUMERAL_RE.fullmatch(t)
                if m and t:
                    tag.decompose()
                    continue

            if tag.name == "p":
                first = next(
                    (
                        n
                        for n in tag.children
                        if isinstance(n, NavigableString) and str(n).strip()
                    ),
                    None,
                )
                if first:
                    node_str = str(first)
                    node_new = re.sub(r"^[\u00a0\u200b\ufeff\s]+", "", node_str)
                    if node_new != node_str:
                        first.replace_with(NavigableString(node_new))

        return str(soup)
    except Exception:
        return html


# ============================================================================
# INLINE STIL ČIŠĆENJE
# ============================================================================
_INLINE_COLOUR_PROPS = re.compile(
    r'\b(?:color|background(?:-color)?|font-(?:color|size)|text-decoration-color)\s*:[^;"}]+[;]?',
    re.IGNORECASE,
)


def _ukloni_inline_stilove(html_fajlovi: list, log_fn=None) -> int:
    modificirano = 0
    for fajl in html_fajlovi:
        try:
            original = fajl.read_text("utf-8", errors="ignore")
            if "style=" not in original:
                continue
            parser = (
                "xml" if fajl.suffix.lower() in {".xhtml", ".xml"} else "html.parser"
            )
            soup = BeautifulSoup(original, parser)
            izmijenjeno = False
            for tag in soup.find_all(True):
                stil = tag.get("style", "")
                if not stil:
                    continue
                novi_stil = _INLINE_COLOUR_PROPS.sub("", stil).strip(" ;")
                if novi_stil != stil:
                    izmijenjeno = True
                    if novi_stil:
                        tag["style"] = novi_stil
                    else:
                        del tag["style"]
            if izmijenjeno:
                fajl.write_text(str(soup), encoding="utf-8")
                modificirano += 1
        except Exception:
            continue
    if modificirano and log_fn:
        log_fn(f"🎨 Inline stilovi očišćeni u {modificirano} HTML fajl(ov)a.", "tech")
    return modificirano


# ============================================================================
# MREŽNI SLOJ
# ============================================================================
async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key, attempt=1):
    try:
        try:
            _timeout_ctx = asyncio.timeout(120)
        except AttributeError:
            import contextlib
            _timeout_ctx = contextlib.asynccontextmanager(lambda: (yield))()
        async with _timeout_ctx:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=json_payload,
                timeout=90,
                verify=False,
            )
        try:
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers)
        except (AttributeError, Exception):
            pass

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (429, 425):
            retry_after = resp.headers.get('Retry-After')
            wait = float(retry_after) if retry_after else min(2 ** attempt, 60)
            self.log(f"[{prov_upper}] HTTP 429 — čekam {wait:.0f}s prije ponovnog pokušaja.", "warning")
            await asyncio.sleep(wait)
            if attempt < 3:
                return await self._async_http_post(url, headers, json_payload, prov, prov_upper, key, attempt+1)
            return None
        elif resp.status_code == 412:
            self.log(f"[{prov_upper}] HTTP 412 Nalog suspendiran / billing limit — ključ onemogućen ⛔", "error")
            return None
        elif resp.status_code == 424:
            self.log(f"[{prov_upper}] HTTP 424 Upstream greška veze — preskačem ⏭️", "warning")
            return None
        else:
            safe = resp.text[:200].replace("<", "&lt;").replace(">", "&gt;")
            self.log(f"[{prov_upper}] HTTP {resp.status_code}: {safe}", "tech")
            return None
    except TimeoutError:
        self.log(f"[{prov_upper}] Timeout (120s) — preskačem poziv.", "warning")
        return None
    except Exception as e:
        self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:100]}", "error")
        return None

async def _call_single_provider(
    self, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=2048
):
    key = self.fleet.get_best_key(prov_upper)
    if not key:
        return None, None

    headers = {"Content-Type": "application/json"}

    if prov_upper == "GEMMA":
        combined = f"{sys_content}\n\n{user_prompt}" if sys_content else user_prompt
        messages = [{"role": "user", "content": combined}]
    else:
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt},
        ]

    payload = {
        "model": model,
        "temperature": opt_temp,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    if prov_upper == "GEMINI":
        url = _url_gemini_compat()
        headers["Authorization"] = f"Bearer {key}"
    elif prov_upper == "COHERE":
        url = _url_cohere()
        headers["Authorization"] = f"Bearer {key.strip()}"
        headers["Accept"] = "application/json"
    else:
        url_map = {
            "GROQ": _url_groq(),
            "CEREBRAS": _url_cerebras(),
            "SAMBANOVA": _url_samba(),
            "MISTRAL": _url_mistral(),
            "OPENROUTER": _url_openrouter(),
            "GITHUB": _url_github(),
            "TOGETHER": _url_together(),
            "FIREWORKS": _url_fireworks(),
            "CHUTES": _url_chutes(),
            "HUGGINGFACE": _url_huggingface(),
            "KLUSTER": _url_kluster(),
            "GEMMA": _url_gemma(),
        }
        url = url_map.get(prov_upper, _url_groq())
        headers["Authorization"] = f"Bearer {key.strip()}"
        if prov_upper == "CEREBRAS":
            payload["max_completion_tokens"] = payload.pop("max_tokens")

    lock = await _ensure_provider_lock(prov_upper)
    async with lock:
        n_keys = len(self.fleet.fleet.get(prov_upper, []))
        base_gap = _PROVIDER_MIN_GAP.get(prov_upper, MIN_GAP)
        import math as _math
        effective_gap = base_gap / _math.sqrt(max(1, n_keys))
        gap = max(1.2, effective_gap)
        key_state = _get_key_state(self.fleet, prov_upper, key)

        if key_state is not None:
            rl_min = getattr(key_state, "rate_limit_minute", 0) or 0
            rm_min = getattr(key_state, "remaining_minute", 0) or 0
            if rl_min > 0 and rm_min > 0:
                rpm_ratio = rm_min / rl_min
                if rpm_ratio < 0.30:
                    safe_gap = 60.0 / max(1, rm_min)
                    gap = max(gap, safe_gap * 1.4)
                elif rpm_ratio < 0.50:
                    safe_gap = 60.0 / max(1, rm_min)
                    gap = max(gap, safe_gap * _RPM_THROTTLE_MULTIPLIER)

            rl_day = getattr(key_state, "rate_limit_day", 0) or 0
            rm_day = getattr(key_state, "remaining_day", 0) or 0
            if rl_day > 0 and rm_day > 0:
                rpd_ratio = rm_day / rl_day
                if rpd_ratio < 0.15:
                    rpd_mult = 1.5 + (0.15 - rpd_ratio) / 0.15 * 2.0
                    gap = max(
                        gap, _PROVIDER_MIN_GAP.get(prov_upper, MIN_GAP) * rpd_mult
                    )

        try:
            rpm_used = self.fleet.get_rpm_used(prov_upper, key)
            rpm_limit = self.fleet.get_effective_rpm_limit(prov_upper, key)
            if rpm_limit > 0 and rpm_used >= int(rpm_limit * 0.70):
                remaining_rpm = max(1, rpm_limit - rpm_used)
                internal_gap = 60.0 / remaining_rpm
                gap = max(gap, internal_gap)
        except AttributeError:
            pass

        jitter = random.uniform(_JITTER_MIN, min(_JITTER_MAX, gap * 0.4))
        gap += jitter

        elapsed = time.time() - _LAST_CALLS.get(prov_upper, 0)
        if elapsed < gap:
            await asyncio.sleep(gap - elapsed)
        _LAST_CALLS[prov_upper] = time.time()
        try:
            self.fleet.record_request(prov_upper, key)
        except AttributeError:
            pass

    data = await _async_http_post(self, url, headers, payload, prov_upper, prov_upper, key)
    if not data:
        return None, None

    if prov_upper == "COHERE" and "message" in data:
        raw = data["message"]["content"][0]["text"].strip()
    elif "choices" in data:
        choice = data["choices"][0] if data["choices"] else {}
        msg = choice.get("message") or {}
        raw = msg.get("content") or ""
        raw = raw.strip()
        if not raw:
            self.log(
                f"[{prov_upper}] Prazan odgovor (nema 'message'/'content' u choices).",
                "tech",
            )
            return None, None
    else:
        return None, None

    return raw, f"{prov_upper}—{model}"
# ============================================================================
# CENTRALNI AI DISPATCH — _call_ai_engine (V10.1 OPTIMIZOVAN)
# ============================================================================
async def _call_ai_engine(
    self,
    prompt,
    chunk_idx,
    uloga="LEKTOR",
    filename="",
    sys_override=None,
    tip_bloka="naracija",
):
    """
    Centralni AI dispatch. Sve uloge prolaze ovdje.
    tip_bloka se koristi za adaptive temperature (#26).
    """
    svi = list(self.fleet.fleet.keys())
    svi_upper = {p.upper() for p in svi}

    opt_max_tokens = 2048

    if uloga == "LEKTOR":
        bazna_temp = 0.45
        opt_temp = _adaptive_temp("LEKTOR", tip_bloka, bazna_temp)
        opt_max_tokens = 4096
        _TIER1 = ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER", "CHUTES"]
        _TIER2 = ["FIREWORKS", "HUGGINGFACE", "KLUSTER", "GROQ"]
        _TIER3 = ["OPENROUTER", "GITHUB", "CEREBRAS", "GEMMA"]
        pms = []
        for tier in (_TIER1, _TIER2, _TIER3):
            tier_pms = []
            for up in tier:
                if up not in svi_upper:
                    continue
                if up == "GEMMA":
                    m = self.fleet.get_active_model(up)
                    if m:
                        tier_pms.append((up, m))
                    continue
                m = (
                    self.fleet.get_active_model(up)
                    if up != "GEMINI"
                    else "gemini-2.0-flash"
                )
                if m:
                    tier_pms.append((up, m))
            random.shuffle(tier_pms)
            pms.extend(tier_pms)
        sys_c = sys_override or self._get_lektor_prompt()

    elif uloga == "KOREKTOR":
        opt_temp = _adaptive_temp("KOREKTOR", tip_bloka, 0.22)
        opt_max_tokens = 4096
        _KOREKTOR_PREF = [
            "GROQ", "CEREBRAS", "GEMINI", "MISTRAL", "COHERE", "TOGETHER",
            "SAMBANOVA", "FIREWORKS", "CHUTES", "HUGGINGFACE", "KLUSTER",
            "OPENROUTER", "GITHUB",
        ]
        pms = []
        for up in _KOREKTOR_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = sys_override or self._get_korektor_prompt()

    elif uloga == "PREVODILAC":
        opt_temp = 0.18
        _PREV_PROV = [
            "GROQ", "CEREBRAS", "SAMBANOVA", "GEMINI", "MISTRAL", "OPENROUTER",
            "TOGETHER", "FIREWORKS", "CHUTES", "HUGGINGFACE", "KLUSTER",
            "GITHUB", "GEMMA",
        ]
        pms = []
        for up in _PREV_PROV:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m or "default"))
        random.shuffle(pms)
        sys_c = sys_override or self._get_prevodilac_prompt()

    elif uloga == "VALIDATOR":
        opt_temp = 0.05
        _VAL_PREF = [
            "GROQ", "CEREBRAS", "GEMINI", "MISTRAL", "TOGETHER", "SAMBANOVA",
            "FIREWORKS", "CHUTES", "HUGGINGFACE", "KLUSTER", "OPENROUTER", "GITHUB",
        ]
        pms = []
        for up in _VAL_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = sys_override or _VALIDATOR_SYS

    elif uloga == "ANALIZA":
        opt_temp = 0.1
        _ANALIZA_PREF = [
            "GEMINI", "GROQ", "CEREBRAS", "TOGETHER", "FIREWORKS", "CHUTES",
            "KLUSTER", "MISTRAL", "COHERE", "SAMBANOVA",
        ]
        pms = []
        for up in _ANALIZA_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = _ANALIZA_SYS

    elif uloga == "GUARDIAN":
        opt_temp = _adaptive_temp("GUARDIAN", tip_bloka, 0.1)
        opt_max_tokens = 4096
        _GUARDIAN_PREF = ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "CHUTES"]
        pms = []
        for up in _GUARDIAN_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = sys_override or self._get_guardian_prompt()

    elif uloga == "POLISH":
        opt_temp = _adaptive_temp("POLISH", tip_bloka, 0.70)
        opt_max_tokens = 4096
        _POLISH_PREF = ["GEMINI", "MISTRAL", "COHERE", "TOGETHER", "CHUTES"]
        pms = []
        for up in _POLISH_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = sys_override or self._get_polish_prompt(tip_bloka=tip_bloka)

    elif uloga == "SCORER":
        opt_temp = 0.05
        opt_max_tokens = 128
        _SCORER_PREF = ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL", "SAMBANOVA"]
        pms = []
        for up in _SCORER_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = _SCORER_SYS

    elif uloga == "CHAPTER_SUMMARY":
        opt_temp = 0.30
        opt_max_tokens = 300
        _SUMMARY_PREF = ["GROQ", "CEREBRAS", "GEMINI", "SAMBANOVA", "MISTRAL"]
        pms = []
        for up in _SUMMARY_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = _CHAPTER_SUMMARY_SYS

    elif uloga == "GLOSAR_UPDATE":
        opt_temp = 0.1
        opt_max_tokens = 600
        _GLOSAR_PREF = ["GEMINI", "GROQ", "CEREBRAS", "MISTRAL", "SAMBANOVA"]
        pms = []
        for up in _GLOSAR_PREF:
            if up not in svi_upper:
                continue
            m = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if m:
                pms.append((up, m))
        sys_c = _GLOSAR_UPDATE_SYS

    else:
        return None, "N/A"

    if not pms:
        return None, "N/A"

    for pokusaj in range(5):
        if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
            return None, "N/A"
        for prov_upper, model in pms:
            raw, label = await _call_single_provider(
                self,
                prov_upper,
                model,
                sys_c,
                prompt,
                opt_temp,
                max_tokens=opt_max_tokens,
            )
            if raw:
                return raw, label
        wait = min(12 * (2**pokusaj), 120) + random.uniform(0, 4)
        self.log(
            f"[Pokušaj {pokusaj + 1}/5] Motori zauzeti. Čekam {wait:.0f}s ⏳",
            "warning",
        )
        await asyncio.sleep(wait)

    return None, "N/A"


# ============================================================================
# ANALIZA KNJIGE
# ============================================================================
async def analiziraj_knjigu(self, intro_text: str):
    cache_file = self.checkpoint_dir / "book_analysis.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text("utf-8"))
            self.book_context.update(cached)
            self.knjiga_analizirana = True
            self.glosar_tekst = self._build_glosar_tekst()
            likovi = ", ".join(list(self.book_context.get("likovi", {}).keys())[:5])
            self.log(
                f"📂 Analiza učitana iz cache-a<br>"
                f"📚 Žanr: <b>{self.book_context.get('zanr')}</b> | "
                f"Ton: <b>{self.book_context.get('ton')}</b><br>"
                f"👥 Likovi: {likovi or '—'}<br>"
                f"✍️ Stilski vodič aktivan",
                "system",
            )
            return
        except Exception:
            pass

    self.shared_stats["status"] = "ANALIZA KNJIGE..."
    self.log("🔬 Analiziram kontekst + stilski vodič...", "system")
    clean = BeautifulSoup(intro_text, "html.parser").get_text()[:2500]
    raw, engine = await _call_ai_engine(self, clean, 0, uloga="ANALIZA")
    if raw:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            ctx = json.loads(m.group() if m else raw)
            self.book_context.update(ctx)
            self.knjiga_analizirana = True
            self.glosar_tekst = self._build_glosar_tekst()
            self._atomic_write(
                cache_file,
                json.dumps(self.book_context, ensure_ascii=False, indent=2),
            )
            likovi = ", ".join(list(self.book_context.get("likovi", {}).keys())[:5])
            self.log(
                f"✅ Analiza završena sa stilskim vodičem ({engine})<br>"
                f"📚 Žanr: <b>{self.book_context.get('zanr')}</b> | "
                f"Ton: <b>{self.book_context.get('ton')}</b><br>"
                f"👥 Likovi: {likovi or '—'}",
                "system",
            )
        except Exception as e:
            self.log(
                f"Analiza — JSON parse greška: {e}. Nastavljam s defaultima.",
                "warning",
            )
    else:
        self.log("Analiza nije dala odgovor. Nastavljam s defaultima.", "warning")


async def _inkrementalna_analiza_glosara(
    self, poglavlje_tekst: str, poglavlje_ime: str
):
    """
    #25: Svaka GLOSAR_UPDATE_INTERVAL poglavlja, analiza traži nove likove/termine
    i merguje ih u postojeći glosar.
    """
    try:
        postoji_glosar = json.dumps(
            {
                "likovi": list(self.book_context.get("likovi", {}).keys()),
                "glosar": list(self.book_context.get("glosar", {}).keys()),
            },
            ensure_ascii=False,
        )
        clean = BeautifulSoup(poglavlje_tekst, "html.parser").get_text()[:2000]
        prompt = (
            f"POSTOJEĆI GLOSAR (ne ponavljaj ove unose):\n{postoji_glosar}\n\n"
            f"NOVI DIO TEKSTA:\n{clean}"
        )
        raw, engine = await _call_ai_engine(self, prompt, 0, uloga="GLOSAR_UPDATE")
        if not raw:
            return

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return
        obj = json.loads(m.group())

        novi_likovi = obj.get("novi_likovi", {})
        novi_termini = obj.get("novi_termini", {})
        dodano = 0

        if isinstance(novi_likovi, dict):
            for k, v in novi_likovi.items():
                if k and k not in self.book_context["likovi"]:
                    self.book_context["likovi"][k] = v
                    dodano += 1

        if isinstance(novi_termini, dict):
            for k, v in novi_termini.items():
                if k and k not in self.book_context["glosar"]:
                    self.book_context["glosar"][k] = v
                    dodano += 1

        if dodano > 0:
            self.glosar_tekst = self._build_glosar_tekst()
            cache_file = self.checkpoint_dir / "book_analysis.json"
            self._atomic_write(
                cache_file,
                json.dumps(self.book_context, ensure_ascii=False, indent=2),
            )
            self.log(
                f"📖 Glosar ažuriran ({engine}): +{dodano} novih unosa (poglavlje {poglavlje_ime})",
                "tech",
            )
    except Exception as e:
        self.log(f"⚠️ Inkrementalna glosar analiza neuspješna: {e}", "warning")


async def _generiraj_chapter_summary(self, file_name: str, file_content: str):
    """
    #24: Generira kratki sažetak poglavlja za kontekst u sljedećem poglavlju.
    """
    try:
        clean = BeautifulSoup(file_content, "html.parser").get_text()[:3000]
        raw, _ = await _call_ai_engine(
            self,
            f"Napiši sažetak ovog poglavlja:\n{clean}",
            0,
            uloga="CHAPTER_SUMMARY",
        )
        if raw:
            summary = _agresivno_cisti(raw).strip()
            self._chapter_summaries[file_name] = summary
            self._save_chapter_summaries()
            self.log(f"📝 Chapter summary generiran: {file_name}", "tech")
    except Exception as e:
        self.log(f"⚠️ Chapter summary neuspješan ({file_name}): {e}", "warning")


# ============================================================================
# V10.1 OPTIMIZOVANI RESCUE MEHANIZAM (Samo GEMINI i MISTRAL)
# ============================================================================
async def _spasi_od_sirovog(
    self,
    sirovo: str,
    chunk: str,
    chunk_idx: int,
    file_name: str,
    prev_ctx: str,
    rel_glosar: str,
    razlog: str,
    tip_bloka: str = "naracija",
):
    PROV_REDOSLJED = ["GEMINI", "MISTRAL"]
    TEMP_LADDER = [0.60, 0.75]
    
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}

    chapter_summary = self._get_chapter_summary_for_lektor(file_name)
    lek_sys = self._get_lektor_prompt(
        prev_kraj=prev_ctx,
        glosar_injekcija=rel_glosar,
        chapter_summary=chapter_summary,
    )
    p_lek = (
        f"IZVORNI TEKST (referenca):\n{chunk}\n\n"
        f"TEKST ZA LEKTURU (ima problem: {razlog}):\n{sirovo}\n\n"
        f"Izvrši AGRESIVNU ponovnu lekturu: ispravi SVE greške, "
        f"ukloni engleske ostatke i vrati prirodan bosanski/hrvatski tekst."
    )

    for temp in TEMP_LADDER:
        for up in PROV_REDOSLJED:
            if up not in svi_upper:
                continue
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return None, None
            m_name = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            if not m_name:
                m_name = "default"
            raw_s, label_s = await _call_single_provider(
                self, up, m_name, lek_sys, p_lek, temp, max_tokens=4096
            )
            if not raw_s:
                continue
            
            kand = _smart_extract(raw_s)

            if (
                kand
                and not _je_placeholder(kand)
                and _detektuj_en_ostatke(kand) <= 0.12
                and not _detektuj_halucinaciju(chunk, kand, uloga="LEKTOR")
            ):
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ✅ Spašeno od sirovog "
                    f"(temp={temp}, {label_s}) | razlog: {razlog}",
                    "info",
                )
                return kand, label_s

    self.log(
        f"[{file_name}] Blok {chunk_idx}: ⛔ Svi rescue pokušaji propali — zadržavam sirovi.",
        "warning",
    )
    return None, None


# ============================================================================
# #14 + V10.1: PIPELINE — process_chunk_with_ai (OPTIMIZOVAN)
# ============================================================================
async def process_chunk_with_ai(
    self, chunk: str, prev_ctx: str, next_ctx: str, chunk_idx: int, file_name: str
) -> tuple:
    chk_fajl = self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"

    if chk_fajl.exists():
        try:
            zapamceno = chk_fajl.read_text("utf-8", errors="ignore")
            if len(zapamceno) > 10 and _detektuj_en_ostatke(zapamceno) < 0.08:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Učitan iz cache-a.",
                    "tech",
                )
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return zapamceno, "DATABASE"
        except Exception:
            pass

    if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
        return None, "N/A"

    jezik = self._detect_language(chunk)
    rel_glosar = self._extract_relevant_glossary(chunk)
    tip_bloka = _detektuj_tip_bloka(chunk)
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)

    # ── KORAK 1: FUSION prijevod+lektura (jedan AI poziv) ─────────────────
    if jezik == "HR":
        sirovo, prov1 = chunk, "AUTO-HR (Bypass)"
        cist_chunk = re.sub(r"<[^>]+>", "", chunk)
        if not any(c in _HR_DIACRITICALS for c in cist_chunk):
            en_score = _detektuj_en_ostatke(chunk)
            if en_score > 0.05:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚠️ HR-bypass bez dijakritika "
                    f"(en_score={en_score:.2f}) — moguć EN propust.",
                    "warning",
                )
        self.log(f"[{file_name}] Blok {chunk_idx}: HR, bypass.", "info")
        sirovo = _automatska_korekcija(sirovo)
        finalno = _post_process_tipografija(sirovo)
        self._atomic_write(chk_fajl, finalno)
        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji
        self.shared_stats["spaseno_iz_checkpointa"] = self.spaseno_iz_checkpointa
        return finalno, "AUTO-HR"
    else:
        fusion_sys = self._get_prevodilac_prompt(
            glosar_chunk=rel_glosar, prev_kraj=prev_ctx
        )
        p_fusion = f"Engleski tekst za prevod:\n{chunk}"

        _FUSION_PROV = [
            "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER",
            "GROQ", "CEREBRAS",
        ]
        svi_upper = {p.upper() for p in self.fleet.fleet.keys()}
        fusion_pms = []
        for up in _FUSION_PROV:
            if up not in svi_upper:
                continue
            m_name = (
                "gemini-2.0-flash"
                if up == "GEMINI"
                else self.fleet.get_active_model(up)
            )
            if m_name:
                fusion_pms.append((up, m_name))

        raw_fusion = None
        prov1 = "FUSION-MISS"
        for fp, fm in fusion_pms:
            raw_f, lbl_f = await _call_single_provider(
                self, fp, fm, fusion_sys, p_fusion, 0.35, max_tokens=4096
            )
            if raw_f and len(re.sub(r"<[^>]+>", "", raw_f).strip()) > 20:
                raw_fusion = _agresivno_cisti(raw_f)
                prov1 = lbl_f
                break

        if not raw_fusion:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: Fusion miss — fallback na PREVODILAC.",
                "warning"
            )
            prev_sys_fb = self._get_prevodilac_prompt(glosar_chunk=rel_glosar)
            p_prevod_fb = f"Prevedi na bosanski/hrvatski:\n{chunk}"
            raw_fb, prov1 = await _call_ai_engine(
                self,
                p_prevod_fb,
                chunk_idx,
                uloga="PREVODILAC",
                filename=file_name,
                tip_bloka=tip_bloka,
            )
            if not raw_fb:
                self.chunk_skips += 1
                self.shared_stats["skipped"] = str(self.chunk_skips)
                return None, "N/A"
            raw_fusion = _agresivno_cisti(raw_fb)

        if _detektuj_en_ostatke(raw_fusion) > 0.25:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Fusion vratio >25% EN — forsiran LEKTOR pass.",
                "warning"
            )
            lek_sys_fb = self._get_lektor_prompt(
                prev_kraj=prev_ctx,
                glosar_injekcija=rel_glosar,
                chapter_summary=chapter_summary,
            )
            p_lek_fb = (
                f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
                f"LOŠ PRIJEVOD (previše engleskog):\n{raw_fusion}\n\n"
                f"Ispravi i vrati čist bosanski/hrvatski tekst."
            )
            raw_lek_fb, prov_lek_fb = await _call_ai_engine(
                self,
                p_lek_fb,
                chunk_idx,
                uloga="LEKTOR",
                filename=file_name,
                sys_override=lek_sys_fb,
                tip_bloka=tip_bloka,
            )
            if raw_lek_fb:
                raw_fusion = _smart_extract(raw_lek_fb)
                prov1 = f"{prov1}→LEKTOR({prov_lek_fb})"

        sirovo = raw_fusion

    # ── KORAK 2: VALIDATOR (samo STANDARD i PREMIUM mod) ─────────────────
    if jezik != "HR" and self.pipeline_mode in ("STANDARD", "PREMIUM"):
        val_prompt = (
            f"ORIGINAL (EN):\n{chunk[:800]}\n\nPRIJEVOD (HR/BS):\n{sirovo[:800]}"
        )
        val_raw, _ = await _call_ai_engine(
            self, val_prompt, chunk_idx, uloga="VALIDATOR", filename=file_name
        )
        if val_raw:
            try:
                m = re.search(r"\{.*\}", val_raw, re.DOTALL)
                val_obj = json.loads(m.group() if m else val_raw)
                if not val_obj.get("ok", True):
                    razlog = val_obj.get("razlog", "nepoznat razlog")
                    self.log(
                        f"Validator: Blok {chunk_idx} odbijen ({razlog}) — retry",
                        "validator",
                    )
                    retry_p = (
                        f"Prethodni prijevod imao grešku: {razlog}\n"
                        f"Ispravi i ponovi:\n```\n{chunk}\n```"
                    )
                    retry_raw, prov1 = await _call_ai_engine(
                        self,
                        retry_p,
                        chunk_idx,
                        uloga="PREVODILAC",
                        filename=file_name,
                        tip_bloka=tip_bloka,
                    )
                    if retry_raw:
                        sirovo = _agresivno_cisti(retry_raw)
            except Exception:
                pass

    # ── KORAK 3: LEKTOR (dodatni prolaz samo u PREMIUM modu) ────────────
    lek_sys = self._get_lektor_prompt(
        prev_kraj=prev_ctx,
        glosar_injekcija=rel_glosar,
        chapter_summary=chapter_summary,
    )
    p_lek = (
        f"IZVORNI ENGLESKI TEKST (referenca za sadržaj — ne prevoditi ponovo):\n{chunk}\n\n"
        f"SIROVI MAŠINSKI PRIJEVOD (tekst koji trebaš lektorirati):\n{sirovo}\n\n"
        f"ZADATAK: Izvrši kompletnu profesionalnu lekturu. Obavezno:\n"
        f"(a) Zamijeni SVA mašinska kalkiranja prirodnim B/H/S izrazima.\n"
        f"(b) Ispravi red riječi koji kopira engleski sintaktički red.\n"
        f"(c) Zamijeni pasivne konstrukcije aktivom gdje je prirodnije.\n"
        f"(d) Uskladi glagolska vremena i vidove kroz cijeli odlomak.\n"
        f"(e) Varij glagole atribucije dijaloga (reče/odvrati/promrmlja/upita).\n"
        f"(f) Pojačaj vokabular — zamijeni generičke opise preciznijim.\n"
        f"REZULTAT mora biti print-ready tekst koji ne odaje mašinsko porijeklo."
    )
    raw_l, prov2 = await _call_ai_engine(
        self,
        p_lek,
        chunk_idx,
        uloga="LEKTOR",
        filename=file_name,
        sys_override=lek_sys,
        tip_bloka=tip_bloka,
    )

    finalno = ""
    if raw_l:
        finalno = _smart_extract(raw_l)

    if not finalno:
        self.log(
            f"[{file_name}] Blok {chunk_idx}: Lektor nije odgovorio — retry sa alt. temperaturom.",
            "warning",
        )
        retry_lek_sys = self._get_lektor_prompt(
            prev_kraj=prev_ctx,
            glosar_injekcija=rel_glosar,
            chapter_summary=chapter_summary,
        )
        retry_p_lek = (
            f"IZVORNI TEKST (referenca):\n{chunk}\n\n"
            f"TEKST ZA LEKTURU:\n{sirovo}\n\n"
            f"Izvrši dubinsku lekturu: (a) ispravi kalkirane i doslovno prevedene konstrukcije, "
            f"(b) uskladi glagolska vremena unutar odlomka, "
            f"(c) poboljšaj ritam dijaloga da zvuči prirodno na bosanskom/hrvatskom."
        )
        svi = list(self.fleet.fleet.keys())
        svi_upper_retry = {p.upper() for p in svi}
        pms_retry = []
        for up in ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "GROQ"]:
            if up not in svi_upper_retry:
                continue
            m_name = (
                self.fleet.get_active_model(up)
                if up != "GEMINI"
                else "gemini-2.0-flash"
            )
            pms_retry.append((up, m_name or "default"))
        for prov_r, model_r in pms_retry:
            raw_retry, label_r = await _call_single_provider(
                self,
                prov_r,
                model_r,
                retry_lek_sys,
                retry_p_lek,
                _adaptive_temp("LEKTOR", tip_bloka, 0.80),
                max_tokens=4096,
            )
            if raw_retry:
                kandidat_r = _smart_extract(raw_retry)
                if kandidat_r and not _je_placeholder(kandidat_r):
                    finalno = kandidat_r
                    prov2 = label_r
                    break

    if not finalno:
        finalno, prov2 = sirovo, f"{prov1}(FS)"

    finalno = _ocisti_ai_markere(finalno)

    # ── PROVJERA VELIČINE ──────────────────────────────────────────────────
    finalno_tekst = re.sub(r"<[^>]+>", "", finalno)
    if len(finalno_tekst.strip()) < 20:
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ⚠️ Rezultat premali ({len(finalno_tekst)} znakova) — koristim original.",
            "warning",
        )
        finalno = chunk
    elif _detektuj_en_ostatke(finalno) > 0.15:
        self.log(
            f"[{file_name}] Blok {chunk_idx}: 🧹 Detektovano >15% engleskog — čistim ostatke.",
            "warning",
        )
        finalno = _agresivno_cisti(finalno)
        if _detektuj_en_ostatke(finalno) > 0.15:
            spas, spas_label = await _spasi_od_sirovog(
                self,
                sirovo,
                chunk,
                chunk_idx,
                file_name,
                prev_ctx,
                rel_glosar,
                "previše engleskog i nakon čišćenja",
                tip_bloka=tip_bloka,
            )
            if spas:
                finalno = spas
                prov2 = spas_label
            else:
                finalno = sirovo

    # ── HALUCINACIJA CHECK ─────────────────────────────────────────────────
    h_detected = _detektuj_halucinaciju(chunk, finalno, uloga="LEKTOR")
    if h_detected:
        orig_len = len(re.sub(r"<[^>]+>", "", chunk))
        prev_len = len(re.sub(r"<[^>]+>", "", finalno))
        ratio = prev_len / orig_len if orig_len else 1

        if ratio < 0.08 or ratio > 6.0:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚡ GIGANTSKA halucinacija (ratio={ratio:.2f}) — pokušavam rescue!",
                "error",
            )
            spas, spas_label = await _spasi_od_sirovog(
                self,
                sirovo,
                chunk,
                chunk_idx,
                file_name,
                prev_ctx,
                rel_glosar,
                f"gigantska halucinacija ratio={ratio:.2f}",
                tip_bloka=tip_bloka,
            )
            if spas:
                finalno = spas
                prov2 = spas_label
            else:
                finalno = sirovo
        else:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju (ratio={ratio:.2f}), puštam dalje.",
                "warning",
            )

    # ── POST-LEKTOR VALIDATOR ─────────────────────────────────────────────
    sirovo_len = len(re.sub(r"<[^>]+>", "", sirovo).strip())
    lektorirani_len = len(re.sub(r"<[^>]+>", "", finalno).strip())
    plv_ratio = lektorirani_len / sirovo_len if sirovo_len > 0 else 1.0
    plv_en = _detektuj_en_ostatke(finalno)
    finalno_cist = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", finalno).strip().lower())
    sirovo_cist = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sirovo).strip().lower())
    lektor_identican = finalno_cist == sirovo_cist
    plv_treba = (
        self.pipeline_mode == "PREMIUM"
        and sirovo_len > 40
        and (
            lektor_identican
            or (
                finalno != sirovo
                and (plv_ratio < 0.88 or plv_ratio > 1.15 or plv_en > 0.02)
            )
        )
    )
    if plv_treba:
        self.log(
            f"[{file_name}] Blok {chunk_idx}: 🔍 Post-lektor validator (ratio={plv_ratio:.2f}, en={plv_en:.2f})",
            "validator",
        )
        plv_prompt = (
            f"PRIJEVOD (sirovi, prije lekture):\n{sirovo}\n\n"
            f"LEKTORIRANI TEKST:\n{finalno}"
        )
        plv_raw, _ = await _call_ai_engine(
            self,
            plv_prompt,
            chunk_idx,
            uloga="VALIDATOR",
            filename=file_name,
            sys_override=_POST_LEKTOR_VALIDATOR_SYS,
        )
        if plv_raw:
            try:
                m_plv = re.search(r"\{.*\}", plv_raw, re.DOTALL)
                plv_obj = json.loads(m_plv.group() if m_plv else plv_raw)
                if not plv_obj.get("ok", True):
                    razlog_plv = plv_obj.get("razlog", "nepoznat razlog")
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: ↩️ Post-lektor rollback ({razlog_plv}) — čuvam sirovi prijevod.",
                        "warning",
                    )
                    finalno = sirovo
            except Exception as exc:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚠️ Post-lektor validator parse greška: {exc}",
                    "warning",
                )

    # ── KOREKTOR (samo PREMIUM mod) ───────────────────────────────────────
    finalno_tekst_len = len(re.sub(r"<[^>]+>", "", finalno).strip())
    if self.pipeline_mode == "PREMIUM" and finalno_tekst_len > 80:
        kor_prompt = f"Tekst za korekturu:\n{finalno}"
        raw_k, prov3 = await _call_ai_engine(
            self,
            kor_prompt,
            chunk_idx,
            uloga="KOREKTOR",
            filename=file_name,
            tip_bloka=tip_bloka,
        )
        if raw_k:
            korektura = _smart_extract(raw_k)
            if (
                korektura
                and not _je_placeholder(korektura)
                and not _detektuj_halucinaciju(finalno, korektura, uloga="LEKTOR")
            ):
                finalno = korektura
                prov2 = f"{prov2}→{prov3}(K)"

    # ── CONSISTENCY GUARDIAN (samo PREMIUM mod) ───────────────────────────
    if (
        self.pipeline_mode == "PREMIUM"
        and len(re.sub(r"<[^>]+>", "", finalno).strip()) > 120
    ):
        guard_raw, _ = await _call_ai_engine(
            self,
            finalno,
            chunk_idx,
            uloga="GUARDIAN",
            filename=file_name,
            tip_bloka=tip_bloka,
        )
        if guard_raw:
            guard_clean = _agresivno_cisti(guard_raw)
            if not _detektuj_halucinaciju(finalno, guard_clean, uloga="LEKTOR"):
                finalno = guard_clean
            else:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚠️ Guardian halucinacija — zadržavam pre-guardian tekst.",
                    "warning",
                )

    # ── HUMAN-LIKE POLISH (samo PREMIUM mod) ─────────────────────────────
    raw_polish = None
    if self.pipeline_mode == "PREMIUM":
        polish_sys = self._get_polish_prompt(tip_bloka=tip_bloka)
        p_polish = f"Tekst za finalni human polish:\n{finalno}"
        raw_polish, prov_polish = await _call_ai_engine(
            self,
            p_polish,
            chunk_idx,
            uloga="POLISH",
            filename=file_name,
            sys_override=polish_sys,
            tip_bloka=tip_bloka,
        )
    
    pre_polish = finalno
    if raw_polish:
        polish_clean = _agresivno_cisti(raw_polish)

        polish_ok = True
        if len(re.sub(r"<[^>]+>", "", polish_clean).strip()) > 40:
            ppv_prompt = f"PRE-POLISH:\n{finalno}\n\nPOST-POLISH:\n{polish_clean}"
            ppv_raw, _ = await _call_ai_engine(
                self,
                ppv_prompt,
                chunk_idx,
                uloga="VALIDATOR",
                filename=file_name,
                sys_override=_POST_POLISH_VALIDATOR_SYS,
            )
            if ppv_raw:
                try:
                    m_ppv = re.search(r"\{.*?\}", ppv_raw, re.DOTALL)
                    ppv_obj = json.loads(m_ppv.group() if m_ppv else ppv_raw)
                    if not ppv_obj.get("ok", True):
                        razlog_ppv = ppv_obj.get("razlog", "nepoznat razlog")
                        self.log(
                            f"[{file_name}] Blok {chunk_idx}: ↩️ Post-Polish rollback ({razlog_ppv})",
                            "warning",
                        )
                        polish_ok = False
                except Exception:
                    pass

        if polish_ok and _detektuj_halucinaciju(finalno, polish_clean, uloga="LEKTOR"):
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Polish halucinacija — rollback na pre-polish.",
                "warning",
            )
            polish_ok = False

        if polish_ok:
            finalno = polish_clean
            prov2 = f"{prov2}→POLISH"
        else:
            finalno = pre_polish

    # ── ZAVRŠNA PROVJERA ──────────────────────────────────────────────────
    if _detektuj_en_ostatke(finalno) > 0.04:
        finalno = _agresivno_cisti(finalno)

    # ── #27: QUALITY SCORING ──────────────────────────────────────────────
    finalno_tekst_final = re.sub(r"<[^>]+>", "", finalno).strip()
    if len(finalno_tekst_final) > 60:
        ocjena = await _scoruj_kvalitetu(
            finalno, self._call_ai_engine, chunk_idx, file_name, self_obj=self
        )
        self._quality_scores[f"{file_name}_blok_{chunk_idx}"] = ocjena

        if ocjena < _QUALITY_RESCUE_THRESHOLD:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: 🚨 Quality score {ocjena:.1f}/10 (ispod {_QUALITY_RESCUE_THRESHOLD}) — rescue pass!",
                "quality",
            )
            rescue_sys = self._get_lektor_prompt(
                prev_kraj=prev_ctx,
                glosar_injekcija=rel_glosar,
                chapter_summary=chapter_summary,
            )
            rescue_prompt = (
                f"IZVORNI TEKST:\n{chunk}\n\n"
                f"TRENUTNA VERZIJA (quality score {ocjena:.1f}/10 — nije dovoljno dobro):\n{finalno}\n\n"
                f"Izvrši AGRESIVNU ponovnu lekturu. Eliminiraj sve kalkirane konstrukcije, "
                f"pojačaj književnost i ritam. Vrati ISKLJUČIVO JSON."
            )
            rescue_provs = []
            svi_u = {p.upper() for p in self.fleet.fleet.keys()}
            for up in ["GEMINI", "MISTRAL"]:
                if up not in svi_u:
                    continue
                m_n = (
                    self.fleet.get_active_model(up)
                    if up != "GEMINI"
                    else "gemini-2.0-flash"
                )
                if m_n:
                    rescue_provs.append((up, m_n))

            for prov_r2, model_r2 in rescue_provs:
                raw_res, label_res = await _call_single_provider(
                    self,
                    prov_r2,
                    model_r2,
                    rescue_sys,
                    rescue_prompt,
                    _adaptive_temp("LEKTOR", tip_bloka, 0.70),
                    max_tokens=4096,
                )
                if raw_res:
                    rescued = _smart_extract(raw_res)

                    if (rescued and not _je_placeholder(rescued) and 
                        not _detektuj_halucinaciju(chunk, rescued, uloga="LEKTOR")):
                        nova_ocjena = await _scoruj_kvalitetu(
                            rescued, self._call_ai_engine, chunk_idx, file_name, self_obj=self
                        )
                        if nova_ocjena > ocjena:
                            finalno = rescued
                            prov2 = f"{prov2}→RESCUE({label_res})"
                            self._quality_scores[f"{file_name}_blok_{chunk_idx}"] = nova_ocjena
                            self.log(
                                f"[{file_name}] Blok {chunk_idx}: ✅ Rescue poboljšao {ocjena:.1f}→{nova_ocjena:.1f}/10",
                                "quality",
                            )
                        break
        else:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⭐ Quality score: {ocjena:.1f}/10",
                "quality",
            )

    finalno = _post_process_tipografija(finalno)
    self._atomic_write(chk_fajl, finalno)
    self.global_done_chunks += 1
    self.stvarno_prevedeno_u_sesiji += 1
    self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji
    self.shared_stats["spaseno_iz_checkpointa"] = self.spaseno_iz_checkpointa

    aud = (
        f"<div style='border-left:4px solid #0ea5e9; background:#0f172a; "
        f"padding:10px; margin:4px 0; border-radius:4px;'>"
        f"<div style='font-size:0.75em; color:#94a3b8; margin-bottom:4px;'>"
        f"📦 Blok {chunk_idx} | {prov1} → {prov2} | tip: {tip_bloka}</div>"
        f"<div style='display:grid; grid-template-columns:1fr 1fr; gap:8px; "
        f"font-size:0.82em; font-family:monospace;'>"
        f"<div style='color:#64748b;'>EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:70]}…</div>"
        f"<div style='color:#e2e8f0;'>HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:70]}…</div>"
        f"</div></div>"
    )

    self.log("", "accordion", en_text=aud)
    return finalno, f"{prov1}→{prov2}"
# ============================================================================
# process_single_file_worker — V10.1 OPTIMIZOVAN
# ============================================================================
async def process_single_file_worker(self, file_path):
    file_name = file_path.name
    try:
        raw_html = file_path.read_text("utf-8", errors="ignore")
    except Exception:
        return

    chunks = self.chunk_html(raw_html, max_words=450)
    if not chunks:
        return

    orig_soup = BeautifulSoup(raw_html, "html.parser")

    self.shared_stats["current_file"] = file_name
    self.shared_stats["total_file_chunks"] = len(chunks)
    final_parts = []

    if file_name not in self._chapter_order:
        self._chapter_order.append(file_name)

    for i, chunk in enumerate(chunks):
        if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
            return

        while self.shared_controls.get("pause"):
            await asyncio.sleep(1)

        p_ctx, n_ctx = self.get_context_window(chunks, i, file_name)
        res, eng = await self.process_chunk_with_ai(chunk, p_ctx, n_ctx, i, file_name)
        final_parts.append(res if res else chunk)

        if (i + 1) % 10 == 0:
            self.buildlive_epub()

        now = time.monotonic()
        if now - self._last_live_epub_time >= 300:
            self.buildlive_epub()
            self._last_live_epub_time = now

        self.shared_stats["current_chunk_idx"] = i + 1
        self.shared_stats["active_engine"] = eng

        try:
            self.shared_stats["current_file_idx"] = self.html_files.index(file_path) + 1
            self.shared_stats["total_files"] = len(self.html_files)
        except Exception:
            pass

        try:
            summary = self.fleet.get_fleet_summary()
            self.shared_stats["fleet_active"] = sum(
                v["active"] for v in summary.values()
            )
            self.shared_stats["fleet_cooling"] = sum(
                v["cooling"] for v in summary.values()
            )
        except Exception:
            pass

        if self.global_total_chunks > 0:
            self.shared_stats["pct"] = int(
                (self.global_done_chunks / self.global_total_chunks) * 100
            )
            self.shared_stats["ok"] = (
                f"{self.global_done_chunks} / {self.global_total_chunks}"
            )

    cijelo_poglavlje = "".join(final_parts)
    await _generiraj_chapter_summary(self, file_name, cijelo_poglavlje)

    body = orig_soup.body
    if body:
        body.clear()
        translated_soup = BeautifulSoup("".join(final_parts), "html.parser")
        for child in list(translated_soup.children):
            body.append(child.extract())
        file_path.write_text(str(orig_soup), encoding="utf-8")
    else:
        file_path.write_text("".join(final_parts), encoding="utf-8")


# ============================================================================
# EPUB OBLIKOVANJE — buildlive_epub, apply_dropcap_and_toc, generate_ncx,
#                    finalize
# ============================================================================
def buildlive_epub(self):
    try:
        live_epub = self.book_path.parent / f"(LIVE)_{self.clean_book_name}.epub"
        self._live_chapter_idx = 0
        with zipfile.ZipFile(live_epub, "w", zipfile.ZIP_DEFLATED) as z:
            m_path = self.work_dir / "mimetype"
            if m_path.exists():
                z.write(m_path, "mimetype", compress_type=zipfile.ZIP_STORED)
            for f in self.work_dir.rglob("*"):
                if (
                    f.is_file()
                    and f.name != "mimetype"
                    and "checkpoints" not in f.parts
                ):
                    if f.suffix.lower() in [".html", ".htm", ".xhtml", ".xml"]:
                        try:
                            soup = BeautifulSoup(
                                f.read_text("utf-8", errors="ignore"), "html.parser"
                            )
                            self.apply_dropcap_and_toc(soup, f, samo_dropcap=True)
                            z.writestr(
                                str(f.relative_to(self.work_dir)),
                                str(soup).encode("utf-8"),
                            )
                        except Exception:
                            z.write(f, f.relative_to(self.work_dir))
                    else:
                        z.write(f, f.relative_to(self.work_dir))
    except Exception:
        pass


def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
    needs_dropcap = True
    _inject_epub_global_css(soup)

    for heading in soup.find_all(["h1", "h2", "h3"]):
        t = heading.get_text(strip=True)
        if not t or "ZADATAK:" in t.upper() or len(t) > 100:
            heading.name = "p"
            continue

        if samo_dropcap:
            self._live_chapter_idx = getattr(self, "_live_chapter_idx", 0) + 1
            chap_num = self._live_chapter_idx
            tid = f"live_ch_{chap_num}_{random.randint(1000, 9999)}"
        else:
            self.chapter_counter += 1
            chap_num = self.chapter_counter
            tid = f"skr_ch_{chap_num}"
            self.toc_entries.append(
                {
                    "title": t,
                    "abs_path": str(html_file),
                    "anchor": tid,
                }
            )

        wrapper = soup.new_tag(
            "div",
            attrs={
                "style": (
                    "page-break-before:always; text-align:center; "
                    "padding-top:15vh; margin-bottom:4vh;"
                )
            },
        )
        heading.wrap(wrapper)

        top_orn = soup.new_tag(
            "div",
            attrs={
                "style": (
                    "color:#8b0000; font-size:1.1em; letter-spacing:0.4em; "
                    "margin-bottom:0.6em; opacity:0.80;"
                )
            },
        )
        top_orn.string = "\u2767 \u2726 \u2767"
        heading.insert_before(top_orn)

        heading["style"] = (
            "text-align:center; "
            "font-family:'Fairy Tail',Palatino,'Book Antiqua',Georgia,serif; "
            "font-size:2.0em; font-weight:bold; font-style:italic; "
            "font-variant:small-caps; letter-spacing:0.10em; "
            "color:#8b0000; margin-bottom:0.5em;"
        )
        heading["id"] = tid

        bot_orn = soup.new_tag(
            "div",
            attrs={
                "style": (
                    "color:#8b0000; font-size:0.95em; letter-spacing:0.4em; "
                    "margin-top:0.6em; opacity:0.75;"
                )
            },
        )
        bot_orn.string = "\u2726 \u2726 \u2726"
        heading.insert_after(bot_orn)

        needs_dropcap = True

    for p in soup.find_all("p"):
        if not needs_dropcap:
            break
        if len(p.get_text(strip=True)) > 40:
            node = next(
                (
                    n
                    for n in p.descendants
                    if isinstance(n, NavigableString) and n.strip()
                ),
                None,
            )
            if node:
                c = node.string.lstrip()
                if not c:
                    continue
                s = soup.new_tag(
                    "span",
                    attrs={
                        "style": (
                            "float:left; font-size:4.2em; line-height:0.78; "
                            "margin-right:0.06em; margin-bottom:0.02em; "
                            "font-family:'Fairy Tail',"
                            "'Book Antiqua',Georgia,serif; "
                            "font-style:italic; font-weight:bold; color:#8b0000;"
                        )
                    },
                )
                o = 2 if c[0] in ["'", '"', "\u201e", "\u201c"] else 1
                s.string = c[:o]
                node.replace_with(c[o:])
                p.insert(0, s)
                needs_dropcap = False


def generate_ncx(self):
    if not self.toc_entries:
        return

    ncx = next(self.work_dir.rglob("*.ncx"), self.work_dir / "OEBPS" / "toc.ncx")
    ncx.parent.mkdir(parents=True, exist_ok=True)

    pts = "".join(
        f'<navPoint id="n{i}" playOrder="{i}">'
        f"<navLabel><text>{e['title']}</text></navLabel>"
        f'<content src="{Path(os.path.relpath(e["abs_path"], ncx.parent)).as_posix()}#{e["anchor"]}"/>'
        f"</navPoint>\n"
        for i, e in enumerate(self.toc_entries, 1)
    )

    ncx.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<ncx xmlns="{_url_daisy()}" version="2005-1">'
        f'<head><meta name="dtb:uid" content="urn:uuid:skr-{self.clean_book_name}"/></head>'
        f"<docTitle><text>{self.book_path.stem}</text></docTitle>"
        f"<navMap>{pts}</navMap></ncx>",
        encoding="utf-8",
    )


def finalize(self):
    self.shared_stats["status"] = "Finalno pakiranje..."

    if self._quality_scores:
        scores = list(self._quality_scores.values())
        avg = sum(scores) / len(scores)
        ispod_praga = sum(1 for s in scores if s < _QUALITY_RESCUE_THRESHOLD)
        self.log(
            f"📊 Quality report — Prosjek: {avg:.1f}/10 | "
            f"Blokova ispod praga {_QUALITY_RESCUE_THRESHOLD}: {ispod_praga}/{len(scores)}",
            "system",
        )

    self.log(
        f"📊 Prevedeno: {self.stvarno_prevedeno_u_sesiji} | "
        f"Iz cache: {self.spaseno_iz_checkpointa} | "
        f"Preskočeno: {self.chunk_skips}",
        "system",
    )

    with zipfile.ZipFile(self.out_path, "w") as z:
        mp = self.work_dir / "mimetype"
        if mp.exists():
            z.write(mp, "mimetype", compress_type=zipfile.ZIP_STORED)
        for f in self.work_dir.rglob("*"):
            if f.is_file() and f.name != "mimetype" and "checkpoints" not in f.parts:
                z.write(
                    f, f.relative_to(self.work_dir), compress_type=zipfile.ZIP_DEFLATED
                )

    self.shared_stats.update(
        {
            "status": "✅ Operacija završena",
            "pct": 100,
            "output_file": self.out_path.name,
        }
    )
    self.log(f"📖 EPUB: {self.out_path.name}", "system")


# ============================================================================
# V10.1: RETROAKTIVNA RE-LEKTURA (sa --force i --only-bad modovima)
# ============================================================================
async def retroaktivna_relektura_v10(
    self,
    target_work_dir: str = None,
    force: bool = False,
    only_bad: bool = False,
    bad_threshold: float = _QUALITY_RESCUE_THRESHOLD,
):
    if target_work_dir:
        self.work_dir = Path(target_work_dir)
    self.checkpoint_dir = self.work_dir / "checkpoints"

    cache_file = self.checkpoint_dir / "book_analysis.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text("utf-8"))
            self.book_context.update(cached)
            self.glosar_tekst = self._build_glosar_tekst()
            self.knjiga_analizirana = True
        except Exception:
            pass

    self._load_chapter_summaries()

    chk_files = sorted(list(self.checkpoint_dir.glob("*.chk")))
    if not chk_files:
        self.log("❌ Nema .chk fajlova.", "error")
        return

    if force:
        mod_opis = "FORCE (sve)"
        ciljani = chk_files
    elif only_bad:
        qs_cache = self.checkpoint_dir / "quality_scores.json"
        prev_scores = {}
        if qs_cache.exists():
            try:
                prev_scores = json.loads(qs_cache.read_text("utf-8"))
            except Exception:
                pass
        ciljani = [
            chk for chk in chk_files if prev_scores.get(chk.stem, 10.0) < bad_threshold
        ]
        mod_opis = f"ONLY-BAD (ispod {bad_threshold:.1f})"
    else:
        mod_opis = "STANDARDNI"
        ciljani = chk_files

    self.log(
        f"🔄 V10.1 Retroaktivna re-lektura [{mod_opis}] + BATCHING {self.BATCH_SIZE} — {len(ciljani)}/{len(chk_files)} blokova",
        "system",
    )

    i = 0
    while i < len(ciljani):
        if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
            break

        batch_size = min(self.BATCH_SIZE, len(ciljani) - i)
        batch_chk = ciljani[i : i + batch_size]
        batch_old_text = []
        batch_file_name = []
        batch_chunk_idx = []

        for chk in batch_chk:
            old_text = chk.read_text("utf-8", errors="ignore")
            file_name = chk.stem.split("_blok_")[0] if "_blok_" in chk.stem else "retro"
            chunk_idx = int(chk.stem.split("_blok_")[-1]) if "_blok_" in chk.stem else i
            batch_old_text.append(old_text)
            batch_file_name.append(file_name)
            batch_chunk_idx.append(chunk_idx)

        batch_prompt = (
            "Izvrši dubinsku V10 lekturu za sljedeće blokove. Vrati JSON array:\n[\n"
        )
        for j in range(len(batch_old_text)):
            batch_prompt += (
                f'  {j}: {{"finalno": "ovdje lekturirani tekst za blok {j}"}},\n'
            )
        batch_prompt += "]\n\nZa svaki blok primijeni sva pravila iz LEKTOR_TEMPLATE-a."

        raw, _ = await self._call_ai_engine(
            batch_prompt,
            batch_chunk_idx[0],
            uloga="LEKTOR",
            filename="retro_batch",
            tip_bloka="naracija",
        )

        batch_finalno = [None] * len(batch_old_text)
        if raw:
            try:
                m = re.search(r"\[.*?\]", raw, re.DOTALL)
                if m:
                    obj = json.loads(m.group())
                    if isinstance(obj, list):
                        for j, item in enumerate(obj):
                            if isinstance(item, dict) and "finalno" in item:
                                batch_finalno[j] = _agresivno_cisti(item["finalno"])
            except Exception:
                pass

        for j, finalno in enumerate(batch_finalno):
            if finalno is None or not finalno:
                finalno = batch_old_text[j]

            chk = batch_chk[j]
            file_name = batch_file_name[j]
            chunk_idx = batch_chunk_idx[j]
            tip_bloka = _detektuj_tip_bloka(finalno)
            rel_glosar = self._extract_relevant_glossary(finalno)
            chapter_summary = self._get_chapter_summary_for_lektor(file_name)

            guard_sys = self._get_lektor_prompt(
                prev_kraj="",
                glosar_injekcija=rel_glosar,
                chapter_summary=chapter_summary,
            )
            guard_raw, _ = await self._call_ai_engine(
                finalno,
                chunk_idx,
                uloga="GUARDIAN",
                filename=file_name,
                sys_override=guard_sys,
                tip_bloka=tip_bloka,
            )
            if guard_raw:
                guard_clean = _agresivno_cisti(guard_raw)
                if not _detektuj_halucinaciju(finalno, guard_clean, uloga="LEKTOR"):
                    finalno = guard_clean

            polish_sys = self._get_polish_prompt(tip_bloka=tip_bloka)
            raw_polish, _ = await self._call_ai_engine(
                f"Tekst za finalni human polish:\n{finalno}",
                chunk_idx,
                uloga="POLISH",
                filename=file_name,
                sys_override=polish_sys,
                tip_bloka=tip_bloka,
            )
            if raw_polish:
                polish_clean = _agresivno_cisti(raw_polish)
                if not _detektuj_halucinaciju(finalno, polish_clean, uloga="LEKTOR"):
                    finalno = polish_clean

            ocjena = await _scoruj_kvalitetu(
                finalno, self._call_ai_engine, chunk_idx, file_name, self_obj=self
            )
            self._quality_scores[chk.stem] = ocjena

            finalno = _post_process_tipografija(_agresivno_cisti(finalno))
            self._atomic_write(chk, finalno)

            self.log(
                f"[{file_name}] Blok {chunk_idx}: ✅ V10.1 retro batch završeno | score: {ocjena:.1f}/10",
                "info",
            )

        i += batch_size

    qs_cache = self.checkpoint_dir / "quality_scores.json"
    self._atomic_write(
        qs_cache,
        json.dumps(self._quality_scores, ensure_ascii=False, indent=2),
    )

    self.log("🔄 Ponovno oblikovanje EPUB-a...", "system")
    for hf in self.html_files:
        try:
            soup = BeautifulSoup(hf.read_text("utf-8", errors="ignore"), "html.parser")
            self.apply_dropcap_and_toc(soup, hf)
            hf.write_text(str(soup), encoding="utf-8")
        except Exception:
            pass
    self.generate_ncx()
    self.finalize()
    self.log(
        "🎉 V10.1 Retroaktivna obrada sa BATCHINGOM završena — najjači mogući kvalitet!",
        "system",
    )


# ============================================================================
# GLAVNA KLASA — SkriptorijAllInOne V10.1
# ============================================================================
class SkriptorijAllInOne:
    GLOSAR_UPDATE_INTERVAL = 5
    BATCH_SIZE = 3

    def __init__(self, book_path, model_name, shared_stats, shared_controls):
        self.book_path = Path(book_path)
        self.model_name = model_name
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls
        self.fleet = FleetManager(config_path="dev_api.json")
        try:
            from api_fleet import register_active_fleet
            register_active_fleet(self.fleet)
        except Exception:
            pass

        self.clean_book_name = re.sub(r"[^a-zA-Z0-9_\-]", "", self.book_path.stem)
        self.work_dir = self.book_path.parent / f"_skr_{self.clean_book_name}"
        self.checkpoint_dir = self.work_dir / "checkpoints"
        self.out_path = self.book_path.parent / f"PREVEDENO_{self.clean_book_name}.epub"

        self.book_context = {
            "zanr": "nepoznat",
            "ton": "neutralan",
            "stil_pripovijedanja": "3. lice",
            "period": "suvremeni",
            "likovi": {},
            "glosar": {},
            "stilski_vodic": "Književni stil prilagođen žanru i tonu.",
        }
        self.knjiga_analizirana = False
        self.glosar_tekst = ""

        self._chapter_summaries: dict = {}
        self._chapter_order: list = []
        self._chapters_processed = 0

        self.toc_entries, self.chapter_counter = [], 0
        self.global_total_chunks = self.global_done_chunks = 0
        self.stvarno_prevedeno_u_sesiji = self.spaseno_iz_checkpointa = 0
        self.chunk_skips = 0
        self.html_files = []
        self._last_live_epub_time = 0.0

        self._quality_scores: dict = {}

        self.pipeline_mode = getattr(self, "pipeline_mode", "STANDARD")

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.log(
            f"V10.1 Engine inicijaliziran za: {self.book_path.name} [pipeline={self.pipeline_mode}]",
            "tech",
        )

    def log(self, msg, ltype="info", en_text=""):
        add_audit(msg, ltype, en_text, self.shared_stats)

    def _atomic_write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp_{random.randint(10000, 99999)}")
        for old in path.parent.glob(f"{path.stem}.tmp*"):
            try:
                old.unlink()
            except Exception:
                pass
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            self.log(f"Greška pri pisanju {path.name}: {e}", "error")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def _detect_language(self, text):
        cist = re.sub(r"<[^>]+>", "", text)
        if any(c in _HR_DIACRITICALS for c in cist):
            return "HR"
        return "EN" if _detektuj_en_ostatke(text) > 0.08 else "HR"

    def _build_glosar_tekst(self) -> str:
        parts = []
        if self.book_context.get("likovi"):
            parts.append("LIKOVI:")
            for ime, opis in list(self.book_context["likovi"].items())[:15]:
                parts.append(f"  - {ime}: {opis}")
        if self.book_context.get("glosar"):
            parts.append("TERMINI:")
            for term, uputa in list(self.book_context["glosar"].items())[:20]:
                parts.append(f"  - {term}: {uputa}")
        return "\n".join(parts)

    def _extract_relevant_glossary(self, chunk_text: str) -> str:
        if not self.glosar_tekst or not chunk_text:
            return "Nema specifičnog glosara."
        clean = BeautifulSoup(chunk_text, "html.parser").get_text().lower()
        relevant = []
        for line in self.glosar_tekst.split("\n"):
            name = re.split(r"[,\-:–(]", line)[0].strip().lower()
            if len(name) >= 2 and re.search(r"\b" + re.escape(name) + r"\b", clean):
                relevant.append(line)
        return (
            "\n".join(relevant[:25])
            if relevant
            else "Nema relevantnih termina u ovom bloku."
        )

    def _get_chapter_summary_for_lektor(self, current_file_name: str) -> str:
        try:
            idx = self._chapter_order.index(current_file_name)
            if idx > 0:
                prev_name = self._chapter_order[idx - 1]
                summary = self._chapter_summaries.get(prev_name, "")
                if summary:
                    return f"Prethodno poglavlje ({prev_name}): {summary}"
        except (ValueError, IndexError):
            pass
        return "Početak knjige ili kontekst nije dostupan."

    def _save_chapter_summaries(self):
        try:
            cache = self.checkpoint_dir / "chapter_summaries.json"
            self._atomic_write(
                cache,
                json.dumps(
                    {
                        "summaries": self._chapter_summaries,
                        "order": self._chapter_order,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        except Exception:
            pass

    def _load_chapter_summaries(self):
        try:
            cache = self.checkpoint_dir / "chapter_summaries.json"
            if cache.exists():
                data = json.loads(cache.read_text("utf-8"))
                self._chapter_summaries = data.get("summaries", {})
                self._chapter_order = data.get("order", [])
                if self._chapter_summaries:
                    self.log(
                        f"📚 Chapter summaries učitani iz cache-a ({len(self._chapter_summaries)} poglavlja)",
                        "tech",
                    )
        except Exception:
            pass

    def _get_prevodilac_prompt(self, glosar_chunk="", prev_kraj="") -> str:
        ton = self.book_context.get("ton", "neutralan")
        stil = self.book_context.get("stil_pripovijedanja", "3. lice")
        zanr = self.book_context.get("zanr", "nepoznat")
        period = self.book_context.get("period", "suvremeni")
        ton_injekcija = (
            f"Žanr: {zanr} | Ton: {ton} | Period: {period} | Stil: {stil} — "
            f"književni jezik, bogat vokabular, ne novinski registar."
        )
        return _PREVODILAC_TEMPLATE.format(
            ton_injekcija=ton_injekcija,
            glosar_injekcija=glosar_chunk or self.glosar_tekst or "Nema glosara.",
            prev_kraj=(prev_kraj[-300:] if prev_kraj else "— početak —"),
        )

    def _get_lektor_prompt(
        self, prev_kraj="", glosar_injekcija="", chapter_summary=""
    ) -> str:
        zanr = self.book_context.get("zanr", "nepoznat")
        ton = self.book_context.get("ton", "neutralan")
        stil = self.book_context.get("stil_pripovijedanja", "3. lice")
        period = self.book_context.get("period", "suvremeni")
        stilski_vodic = self.book_context.get(
            "stilski_vodic", "Književni stil prilagođen žanru i tonu."
        )
        knjiga_kontekst = (
            f"Žanr: {zanr} | Ton: {ton} | Period: {period} | Narativ: {stil}"
        )
        return _LEKTOR_TEMPLATE.format(
            knjiga_kontekst=knjiga_kontekst,
            stilski_vodic=stilski_vodic,
            glosar_injekcija=glosar_injekcija or self.glosar_tekst or "Nema glosara.",
            prev_kraj=(prev_kraj[-600:] if prev_kraj else "—"),
            chapter_summary=chapter_summary or "Nema chapter konteksta.",
        )

    def _get_korektor_prompt(self) -> str:
        return _KOREKTOR_TEMPLATE

    def _get_guardian_prompt(self) -> str:
        return _GUARDIAN_SYS

    def _get_polish_prompt(self, tip_bloka: str = "naracija") -> str:
        zanr = self.book_context.get("zanr", "nepoznat")
        ton = self.book_context.get("ton", "neutralan")
        stilski = self.book_context.get("stilski_vodic", "")
        return _POLISH_TEMPLATE.format(
            zanr=zanr,
            ton=ton,
            tip_bloka=tip_bloka,
            stilski_vodic=stilski,
        )

    def chunk_html(self, html_content: str, max_words=450) -> list:
        soup = BeautifulSoup(html_content, "html.parser")
        body = soup.body if soup.body else soup
        chunks, current_chunk, current_words = [], [], 0

        for tag in body.children:
            tag_str = str(tag)
            text = (
                tag.get_text(strip=True)
                if not isinstance(tag, NavigableString)
                else str(tag).strip()
            )
            words = len(text.split())
            if words == 0:
                current_chunk.append(tag_str)
                continue
            if current_words + words > max_words and current_words > 0:
                chunks.append("".join(current_chunk))
                current_chunk = [tag_str]
                current_words = words
            else:
                current_chunk.append(tag_str)
                current_words += words

        if current_chunk:
            chunks.append("".join(current_chunk))
        return [c for c in chunks if c.strip()]

    def get_context_window(self, chunks: list, idx: int, file_name: str) -> tuple:
        prev_ctx, next_ctx = "Početak poglavlja.", "Kraj poglavlja."
        if idx > 0:
            prev_chk = self.checkpoint_dir / f"{file_name}_blok_{idx - 1}.chk"
            if prev_chk.exists():
                try:
                    prev_raw = prev_chk.read_text("utf-8")
                    prev_ctx = BeautifulSoup(prev_raw, "html.parser").get_text()[-600:]
                except Exception:
                    prev_ctx = chunks[idx - 1][-600:]
            else:
                prev_ctx = chunks[idx - 1][-600:]
        if idx < len(chunks) - 1:
            next_ctx = chunks[idx + 1][:400]
        return prev_ctx, next_ctx


# Injektuj sve metode u klasu
SkriptorijAllInOne._async_http_post = _async_http_post
SkriptorijAllInOne._call_single_provider = _call_single_provider
SkriptorijAllInOne._call_ai_engine = _call_ai_engine
SkriptorijAllInOne.analiziraj_knjigu = analiziraj_knjigu
SkriptorijAllInOne._inkrementalna_analiza_glosara = _inkrementalna_analiza_glosara
SkriptorijAllInOne._generiraj_chapter_summary = _generiraj_chapter_summary
SkriptorijAllInOne._spasi_od_sirovog = _spasi_od_sirovog
SkriptorijAllInOne.process_chunk_with_ai = process_chunk_with_ai
SkriptorijAllInOne.process_single_file_worker = process_single_file_worker
SkriptorijAllInOne.buildlive_epub = buildlive_epub
SkriptorijAllInOne.apply_dropcap_and_toc = apply_dropcap_and_toc
SkriptorijAllInOne.generate_ncx = generate_ncx
SkriptorijAllInOne.finalize = finalize
SkriptorijAllInOne.retroaktivna_relektura_v10 = retroaktivna_relektura_v10


# ============================================================================
# NO ČIŠĆENJE CHECKPOINT FAJLOVA
# ============================================================================
def _no_cisti_chk_fajlove(checkpoint_dir: Path, log_fn=None) -> int:
    if not checkpoint_dir.exists():
        return 0
    popravljeno = 0
    for chk in checkpoint_dir.glob("*.chk"):
        try:
            sadrzaj = chk.read_text("utf-8", errors="ignore")
            ocisceno = _cisti_json_wrapper(sadrzaj.strip())
            if ocisceno != sadrzaj.strip():
                tmp = chk.with_suffix(f".tmp_{random.randint(10000, 99999)}")
                try:
                    tmp.write_text(ocisceno, encoding="utf-8")
                    tmp.replace(chk)
                    popravljeno += 1
                    if log_fn:
                        log_fn(f"🧹 CHK sanacija: {chk.name}", "tech")
                except Exception as e:
                    if tmp.exists():
                        try:
                            tmp.unlink()
                        except Exception:
                            pass
                    if log_fn:
                        log_fn(
                            f"⚠️ CHK sanacija neuspješna ({chk.name}): {e}", "warning"
                        )
        except Exception:
            continue
    if popravljeno and log_fn:
        log_fn(
            f"✅ na CHK sanacija: {popravljeno} fajl(ov)a popravljeno.",
            "system",
        )
    return popravljeno


# ============================================================================
# START FUNKCIJA
# ============================================================================
def start_skriptorij_from_master(bookpathstr, modelname, sharedstats, shared_controls):
    engine = SkriptorijAllInOne(bookpathstr, modelname, sharedstats, shared_controls)
    engine.log(
        "🚀 V10.1 Omni-Core pokrenut — print-ready + quality scoring aktivan", "system"
    )

    engine.work_dir.mkdir(parents=True, exist_ok=True)
    engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    _no_cisti_chk_fajlove(engine.checkpoint_dir, log_fn=engine.log)

    engine._load_chapter_summaries()

    if engine.book_path.suffix.lower() == ".mobi":
        if not HAS_MOBI:
            engine.log(
                "Greška! MOBI dekoder nije instaliran. Pokrenite: <b>pip install mobi</b>",
                "error",
            )
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
            engine.log("MOBI uspješno konvertovan. Nastavljam V10.1 obradu.", "system")
        except Exception as e:
            engine.log(f"MOBI ekstrakcija neuspješna: {e}", "error")
            sharedstats["status"] = "ZAUSTAVLJENO"
            return
    else:
        with zipfile.ZipFile(engine.book_path, "r") as z:
            z.extractall(engine.work_dir)

    engine.html_files = sorted(
        [
            f
            for f in engine.work_dir.rglob("*")
            if f.suffix.lower() in [".html", ".htm", ".xhtml", ".xml"]
        ],
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
        engine.log(
            f"🧹 HTML pre-processing: {ocisceno_html} fajl(ov)a očišćeno.", "tech"
        )

    for f in engine.html_files:
        try:
            engine.global_total_chunks += len(
                engine.chunk_html(f.read_text("utf-8", errors="ignore"))
            )
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

            engine.log(
                f"📄 Poglavlje {i}/{len(engine.html_files)}: {hf.name}", "system"
            )
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


# ============================================================================
# V10.1 NA RE-LEKTURA — CLI entry point
# ============================================================================
if __name__ == "__main__":
    import sys
    import asyncio
    from pathlib import Path

    force_mode = "--force" in sys.argv
    only_bad_mode = "--only-bad" in sys.argv

    WORK_DIR = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and Path(arg).exists():
            WORK_DIR = arg
            break

    if WORK_DIR is None:
        print("Usage: python skriptorij.py [--force|--only-bad] <work_dir>")
        sys.exit(1)

    shared_stats = {"status": "V10.1 RETRO RE-LEKTURA"}
    shared_controls = {"stop": False, "reset": False, "pause": False}

    engine = SkriptorijAllInOne(
        Path(WORK_DIR).parent / "dummy.epub",
        "dummy",
        shared_stats,
        shared_controls,
    )
    engine.work_dir = Path(WORK_DIR)

    if force_mode:
        print("🚀 Mod: FORCE — sve blokove prolazi kroz V10.1 pipeline")
    elif only_bad_mode:
        print(
            f"🎯 Mod: ONLY-BAD — samo blokove s quality score < {_QUALITY_RESCUE_THRESHOLD}"
        )
    else:
        print("🔄 Mod: STANDARDNI V10.1 retro pass")

    asyncio.run(
        engine.retroaktivna_relektura_v10(
            force=force_mode,
            only_bad=only_bad_mode,
        )
    )