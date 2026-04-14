# ============================================================================
# SKRIPTORIJ V8 OMNI-CORE — skriptorij.py
# Poboljšanja: #5 Rate-limit headeri | #6 asyncio.to_thread | #7 Atomic write
# #8 Exp. backoff | #9 Overlap chunking | #11 Dinamička analiza knjige
# #12 Idiomska zaštita | #13 Konzistentnost tona | #14 Trostepeni pipeline
# #15 AI marker čišćenje | #16 Poboljšana halucinacija | #17 Gemini 2.5
# #18 Bolja temperatura
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
from api_fleet import FleetManager, register_active_fleet

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


def _url_daisy():
    return "http://www.daisy.org/z3986/2005/ncx/"


# ============================================================================
# GLOBALNI RATE LIMITER
# ============================================================================
_GLOBAL_DOOR = None
_LAST_CALLS = {}
# Minimalni razmak između poziva — po provajderu (sekunde).
# Gemini free tier: 15 RPM → 4s; koristimo 5s za sigurnosnu marginu.
# Klíč je prov_upper (ne model!) da bi oba Gemini modela dijelila isti timer.
_PROVIDER_MIN_GAP = {
    "GEMINI":      5.0,
    "GROQ":        3.0,
    "CEREBRAS":    2.5,
    "SAMBANOVA":   3.0,
    "MISTRAL":     3.0,
    "COHERE":      3.0,
    "OPENROUTER":  3.0,
    "GITHUB":      5.0,
    "TOGETHER":    4.0,
    "FIREWORKS":   4.0,
    "CHUTES":      3.5,
    "HUGGINGFACE": 4.0,
    "KLUSTER":     4.0,
}
MIN_GAP = 3.0  # fallback za nepoznate provajdere


async def _ensure_global_lock():
    """Lazy initialization of asyncio Lock in the current event loop."""
    global _GLOBAL_DOOR
    if _GLOBAL_DOOR is None:
        _GLOBAL_DOOR = asyncio.Lock()
    return _GLOBAL_DOOR


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

# Placeholder tekstovi koji AI ponekad doslovno vrati iz template-a
_PLACEHOLDER_STRINGS = frozenset({
    "lektorisani tekst ovdje",
    "korigirani tekst ovdje",
    "<ovdje_idi_lektorirani_tekst>",
    "<ovdje_idi_korigirani_tekst>",
    "ovdje_idi_lektorirani_tekst",
    "ovdje_idi_korigirani_tekst",
    "tekst ovdje",
    "vaš tekst ovdje",
})


def _je_placeholder(tekst: str) -> bool:
    """Vraća True ako tekst izgleda kao echo-back AI template placeholdera."""
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    return cist in _PLACEHOLDER_STRINGS


def _ocisti_ai_markere(tekst: str) -> str:
    for p in _AI_TELLS_PATTERNS:
        tekst = re.sub(p, "", tekst, flags=re.IGNORECASE)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


# ============================================================================
# #19: JSON OMOTAČ ČIŠĆENJE — regex fallback za kad JSON parse ne uspije
# ============================================================================
# Navodnici: standardni " i tipografski „ " ' ' (koje tipografija može ubaciti)
_QUOTE_CHARS = r'["\u201c\u201d\u201e\u2018\u2019]'
_JSON_OMOTAC_RE = re.compile(
    r'^\s*\{\s*'
    + _QUOTE_CHARS + r'?'            # opcionalni otvorni navodnik ključa
    + r'[\w_]+'                      # naziv ključa (npr. finalno_polirano)
    + _QUOTE_CHARS + r'?'            # opcionalni zatvorni navodnik ključa
    + r'\s*:\s*'
    + _QUOTE_CHARS                   # otvorni navodnik vrijednosti
    + r'([\s\S]*?)'                  # sadržaj (non-greedy, multiline)
    + _QUOTE_CHARS + r'?'            # zatvorni navodnik vrijednosti (opcionalan)
    + r'\s*\}\s*$',
    re.DOTALL,
)


def _cisti_json_wrapper(tekst: str) -> str:
    """Izvadi tekst iz JSON omotača koji AI ponekad vraća umjesto čistog teksta.

    Podržava standardne i tipografske navodnike (jer tipografska obrada može
    pretvoriti " u „ prije nego što se otkrije problem).

    Primjeri:
      {"finalno_polirano": "tekst"}  →  "tekst"
      {„finalno_polirano": „tekst"}  →  "tekst"
      {"korektura": "<p>tekst</p>"}  →  "<p>tekst</p>"
    """
    if not tekst:
        return tekst
    stripped = tekst.strip()
    if not stripped.startswith('{'):
        return tekst
    # Korak 1: standardni JSON parse
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and obj:
            val = (
                obj.get("finalno_polirano")
                or obj.get("korektura")
                or next(iter(obj.values()), "")
            )
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        pass
    # Korak 2: regex fallback — hvata i tipografske navodnike
    m = _JSON_OMOTAC_RE.match(stripped)
    if m:
        extracted = m.group(1).strip()
        if extracted:
            return extracted
    return tekst


# ============================================================================
# DETEKCIJA ENGLESKOG
# ============================================================================
_EN_STOPWORDS = frozenset(
    {
        # Original stopwords
        "the", "and", "was", "for", "are", "with", "his", "they", "have",
        "from", "this", "that", "will", "what", "their", "said", "been",
        "which", "into", "but", "not", "she", "her", "had", "him", "its",
        "our", "out", "who", "when", "than", "then", "some", "very", "just",
        "like", "your", "can",
        # Common 2-letter English words (critical for short/title texts)
        "by", "of", "in", "is", "it", "he", "we", "at", "an", "to", "be",
        "as", "or", "do", "if", "no", "my", "us", "am", "go", "up", "so",
        "me", "on", "oh",
        # Common 3-letter English words
        "all", "one", "has", "any", "new", "now", "how", "old", "did", "say",
        "get", "let", "two", "see", "too", "try", "may", "own", "way", "day",
        "man", "big", "got", "set", "few", "off", "yes", "yet", "ago", "far",
        "add", "age", "air", "bad", "bed", "bit", "box", "boy", "car", "cut",
        "end", "eye", "fit", "fun", "god", "guy", "hit", "hot", "job", "key",
        "kid", "law", "leg", "lot", "low", "mad", "mom", "men", "net", "odd",
        "oil", "pay", "run", "sad", "sit", "six", "sky", "son", "sun", "ten",
        "top", "toy", "war", "win", "won", "arm", "ask", "act",
        # Common 4+ letter English words
        "also", "away", "back", "came", "come", "days", "does", "each", "even",
        "ever", "eyes", "face", "feel", "find", "gave", "give", "goes", "good",
        "hand", "here", "home", "keep", "know", "last", "left", "life", "live",
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
        # Common English words often seen in book titles/author sections
        "published", "library", "division", "copyright", "reserved", "rights",
        "author", "edition", "chapter", "volume", "series", "press", "books",
        "fiction", "novel", "story", "tales", "written", "edited", "cover",
    }
)

# Croatian diacritical characters — strong indicator of Croatian/Bosnian text
_HR_DIACRITICALS = frozenset("šćčžđŠĆČŽĐ")


def _detektuj_en_ostatke(tekst: str) -> float:
    try:
        cist = re.sub(r"<[^>]+>", "", tekst).lower()

        # Croatian diacriticals are a strong indicator of Croatian/Bosnian text.
        # If the text has sufficient diacritical density, it is almost certainly
        # not English — return 0.0 immediately so it is kept as-is.
        total_alpha = sum(1 for c in cist if c.isalpha())
        hr_diacritical_count = sum(1 for c in cist if c in _HR_DIACRITICALS)
        if total_alpha > 0 and hr_diacritical_count / total_alpha >= 0.02:
            return 0.0

        # Include 2-letter words to catch short but very common English words
        # (e.g. "by", "of", "in", "is") that appear in titles and captions.
        words = re.findall(r"\b[a-z]{2,}\b", cist)
        if not words:
            return 0.0
        return sum(1 for w in words if w in _EN_STOPWORDS) / len(words)
    except Exception:
        return 0.0


# ============================================================================
# #16: POBOLJŠANA HALUCINACIJA DETEKCIJA
# ===========================================
def _detektuj_halucinaciju(original: str, prijevod: str, uloga: str = "LEKTOR") -> bool:
    """
    Detektuje STVARNE halucinacije — ne odbacuje lektorirane verzije!
    Pragovi su FLEKSIBILNI:
    - PREVODILAC: stroža (ratio 0.15-3.0)
    - LEKTOR: VRLO blaža (ratio 0.1-4.5) — koristi sve što je logično
    """
    try:
        orig_len = len(re.sub(r"<[^>]+>", "", original))
        prev_len = len(re.sub(r"<[^>]+>", "", prijevod))

        # Minimalnost — ako je dovoljno nešto
        if orig_len == 0 or prev_len < 15:
            return False

        ratio = prev_len / orig_len

        # ⚠️ SAMO EKSTREMNI SLUČAJEVI — ne odbacuj lekturu!
        if uloga == "LEKTOR":
            # Lektorirani tekst može biti 10%-450% originala — nije greška!
            if ratio < 0.10 or ratio > 4.5:
                return True
        else:  # PREVODILAC
            # Prijevod mora biti closer
            if ratio < 0.15 or ratio > 3.0:
                return True

        # TEST 2: BESKONAČNA PETLJA — ista rečenica 7+ puta (ne 3!)
        recenice = [
            s.strip() for s in re.split(r"[.!?]", prijevod) if len(s.strip()) > 20
        ]
        counts = Counter(recenice)
        if any(v >= 7 for v in counts.values()):  # ← Povećano na 7
            return True

        # TEST 3: 4-gram ponavljanje — samo ako je doista loše (8+ puta)
        words = re.findall(r"\b\w+\b", prijevod.lower())
        if len(words) > 80:  # ← Povećan na 80 slov, ne 50
            grams = [" ".join(words[i : i + 4]) for i in range(len(words) - 3)]
            counts = Counter(grams)
            if any(v >= 8 for v in counts.values()):  # ← Povećano na 8
                return True

        # Ako prođe sve testove — nije halucinacija!
        return False
    except Exception:
        return False


def _agresivno_cisti(tekst: str) -> str:
    if not tekst:
        return ""
    # Najprije ukloni JSON omotač (ako postoji)
    tekst = _cisti_json_wrapper(tekst)
    patterns = [
        r"https?://googleusercontent\.com/immersive_entry_chip/\d+",
        r"```(?:html|json|text|xml)?\s*",
        r"```\s*$",
        r"ZADATAK:.*?\n",
        r"GLOSAR:.*?\n",
        r"SYSTEM:.*?\n",
        r"\*\*(.*?)\*\*",
        # Zaostali JSON omotači koje regex/json.loads nije uhvatio —
        # uklanjamo samo cijeli obrazac {ključ: "vrijednost"} da se ne zahvate legitimni sadržaji
        r'^\s*\{["\u201c\u201d\u201e]?[\w_]+["\u201c\u201d\u201e]?\s*:\s*["\u201c\u201d\u201e]([\s\S]*?)["\u201c\u201d\u201e]\s*\}\s*$',
        # Placeholder natpisi iz AI template-a
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
        "warning": ("border-left:3px solid #fa0", "background:#310", "color:#fa0"),
        "error": ("border-left:4px solid #f44", "background:#300", "color:#f44"),
        "validator": (
            "border-left:3px solid #10b981",
            "background:#052e16",
            "color:#6ee7b7; font-size:0.85em",
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
    if len(audit_logs) > 250:
        audit_logs.pop(0)
    if shared_stats is not None:
        shared_stats["live_audit"] = "".join(audit_logs)


# ============================================================================
# TIPOGRAFSKA OBRADA — deterministička B/H/S tipografska pravila
# ============================================================================
def _post_process_tipografija(tekst: str) -> str:
    """Primijeni B/H/S tipografska pravila na gotov tekst."""
    # Tri točke → elipsa (…) i višestruke točke
    tekst = re.sub(r'\.\.\.', '…', tekst)
    tekst = re.sub(r'\.{4,}', '…', tekst)

    # Crtica za dijalog: crtica na početku odlomka (after <p> or start of line)
    tekst = re.sub(r'(<p[^>]*>)\s*-\s', r'\1— ', tekst)
    tekst = re.sub(r'(<p[^>]*>)\s*–\s', r'\1— ', tekst)

    # Dvostruki razmaci → jedan razmak (samo u tekstualnim segmentima, izvan HTML tagova)
    def _fix_spaces(m: re.Match) -> str:
        return re.sub(r'  +', ' ', m.group())

    tekst = re.sub(r'(?<=>)([^<]+)(?=<)', _fix_spaces, tekst)
    # Također popravi razmake na početku/kraju dokumenta (izvan tagova)
    tekst = re.sub(r'^([^<]+)', _fix_spaces, tekst)
    tekst = re.sub(r'([^>]+)$', _fix_spaces, tekst)

    # Navodnici: zamijeni "..." sa „..." (B/H/S standard)
    # Koristi HTML-svjesni pristup: samo unutar tekstualnih čvorova (između > i <)
    def _fix_navodnici(m: re.Match) -> str:
        return re.sub(r'"([^"]+)"', r'„\1"', m.group())

    tekst = re.sub(r'(?<=>)([^<]+)(?=<)', _fix_navodnici, tekst)
    # Tekstualni segmenti na početku/kraju dokumenta
    tekst = re.sub(r'^([^<]+)', _fix_navodnici, tekst)
    tekst = re.sub(r'([^>]+)$', _fix_navodnici, tekst)

    # Razmak prije interpunkcije (,.:;!?)
    tekst = re.sub(r'\s+([,;:!?])', r'\1', tekst)

    return tekst


# ============================================================================
# #11 + #12 + #13: SYSTEM PROMPTI — DINAMIČKI
# ============================================================================
_PREVODILAC_TEMPLATE = """\
Ti si iskusni književni prevodilac s engleskog na bosanski/hrvatski jezik s 20+ godina iskustva. \
Tvoji prijevodi objavljuje Fraktura, VBZ i Mozaik knjiga.

ŽELJENI REZULTAT: Tekst koji čitalac doživljava kao da je IZVORNO napisan na bosanskom/hrvatskom.

STROGA PRAVILA:
1. HTML TAGOVI: Zadrži SVE tagove (<p>, <i>, <b>, <em>, <br>, <div>) tačno kakvi su.
2. ČISTOĆA: Vrati SAMO prevedeni tekst. Nula komentara, nula uvoda, nula objašnjenja.
3. PRIJEVODIZMI — ZABRANA: Nikad ne prevodi doslovno fraze koje u B/H/S zvuče neprirodno:
   - "It was..." → ne "Bilo je..." nego nađi prirodniji ekvivalent
   - "He/She found himself/herself..." → "Zatekao/la se...", "Obreo/la se..."
   - "There was/were..." → preformuliraj rečenicu bez krutog "postajati/biti"
   - "As if/As though..." → "Kao da...", "Kao da bi..."
4. IDIOMI — EKVIVALENTI (ne doslovan prijevod):
   "kick the bucket"→"ispustiti dušu" | "piece of cake"→"mačji kašalj" |
   "raining cats and dogs"→"kiša kao iz kabla" | "break a leg"→"sretno" |
   "bite the bullet"→"prihvatiti gorku istinu" | "under the weather"→"bolesno/loše" |
   "spill the beans"→"odati tajnu" | "cost an arm and a leg"→"koštati bogatstvo" |
   "hit the nail on the head"→"pogoditi u metu" | "let the cat out of the bag"→"odati tajnu" |
   "burn bridges"→"spaliti mostove" | "beat around the bush"→"ići oko vrućeg kaše" |
   "elephant in the room"→"tema koju svi izbjegavaju" | "once in a blue moon"→"jednom u sto godina" |
   "barking up the wrong tree"→"udariš u krivu ploču"
5. DIJALOG: Dijalog prevedi prirodno, prilagodi idiome govornom jeziku.
6. TON: {ton_injekcija}
7. GLOSAR LIKOVA I TERMINA (OBAVEZNO KORISTITI):
{glosar_injekcija}
"""

_LEKTOR_TEMPLATE = """\
Ti si Glavni urednik i vrhunski književni lektor koji radi za elitnu izdavačku kuću. \
Tvoj posao je pretvoriti strojni prijevod u tekst koji se čita kao originalna književnost.

KONTEKST KNJIGE: {knjiga_kontekst}

GLOSAR LIKOVA I TERMINA (OBAVEZNO POŠTOVATI — ne mijenjaj ova imena ni pojmove):
{glosar_injekcija}

IMPERATIVNA PRAVILA LEKTURE:

1. KNJIŽEVNI STIL ({stil_injekcija}):
   • Vokabular: koristi bogat, raznovrstan rječnik — izbjegavaj ponavljanje istih glagola i pridjeva
   • Ritam: izmjenjuj kratke i duge rečenice za prirodan ritam čitanja
   • Perspektiva: strogo drži zadanu perspektivu pripovijedanja
   • Registar: prilagodi stil žanru — književni za romansu/dramu, napeti za thriller, poetičan za fantaziju

2. BOSANSKI/HRVATSKI JEZIK — SPECIFIKE:
   • Futur I (napisat ću) i kondicional (napisao bih) — koristi pravilno, ne miješaj
   • Zamjenice: ne prekoristuj "on/ona/ono" — zamijeni imenima kad je jasno
   • Pasiv: zamijeni engleski pasiv aktivnom konstrukcijom gdje god je moguće
   • Glagolski vid: razlikuj perfektivne i imperfektivne glagole

3. DIJALOG I TIPOGRAFIJA:
   • Dijalog počinje crticom: — Zdravo, reče on. (NE navodnicima "Zdravo")
   • Misli likova: u kurzivu <em>Što da radim?</em>
   • Tri točkice: koristi … (ne ...) za pauze i zamišljenost
   • Em-crtica — za umetke i naglasak

4. KONZISTENTNOST:
   • Prethodni odlomak završava: "{prev_kraj}"
   • Nastavi ISTIM glagolskim vremenom, tonom i perspektivom
   • Isti lik govori uvijek ISTIM glasom i idiolektom

5. ZABRANJENO:
   • Uvodni komentari ("Evo prijevoda:", "Naravno!", "Svakako!")
   • Izlišne rečenice koje nisu u originalu
   • Prebukvalni prijevodi koji zvuče neprirodno
   • Mijenjanje ili uklanjanje vlastitih imena i pojmova iz glosara

6. HTML FORMAT:
   • Zadrži SVE HTML tagove (<p>, <em>, <i>, <b>, <br>, <div>) netaknute i na originalnim pozicijama
   • Ne dodaj, ne uklanjaj i ne premještaj tagove

Vrati ISKLJUČIVO JSON objekt: {{"finalno_polirano": "<OVDJE_IDI_LEKTORIRANI_TEKST>"}}
Zamijeni <OVDJE_IDI_LEKTORIRANI_TEKST> stvarnim lektoriranim sadržajem. Ne ponavljaj ovu uputu.
"""

_KOREKTOR_TEMPLATE = """\
Ti si precizni korektor koji priprema rukopis za tisak. \
Tekst je već lektoriran — tvoj je zadatak SAMO tehnička ispravnost. Ne mijenjaj stil ni sadržaj.

PROVJERI I ISPRAVI:

1. GRAMATIKA:
   • Padeži i sklonidba imenica/zamjenica/pridjeva
   • Slaganje subjekta i predikata u rodu i broju
   • Glagolska vremena — dosljednost unutar odlomka

2. INTERPUNKCIJA I TIPOGRAFIJA:
   • Zareze ispred "koji/koja/koje/što" (subordinatne rečenice)
   • Em-crtica (—) za dijalog, en-crtica (–) za raspone, obična crtica (-) za spojnice
   • Tri točkice: … (jedan znak, ne tri odvojena)
   • Navodnici: „tekst" (dolje-gore)
   • Razmaci: nema dvostrukih razmaka, nema razmaka prije interpunkcije

3. KONZISTENTNOST:
   • Ista vlastita imena (nema varijacija za isti lik)
   • Isti termini za iste pojmove
   • Isti glagolski vid u opisima

4. FORMAT: Zadrži SVE HTML tagove netaknute. Ne dodaj novi sadržaj.

Vrati ISKLJUČIVO JSON objekt: {{"korektura": "<OVDJE_IDI_KORIGIRANI_TEKST>"}}
Zamijeni <OVDJE_IDI_KORIGIRANI_TEKST> stvarnim korigiranim sadržajem. Ne ponavljaj ovu uputu.
"""

_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete prijevoda.
Provjeri da li prijevod vjerno prenosi SMISAO originalnog engleskog teksta.
Gledaj samo smisao i nijanse — ne gledaj stil.
Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

_POST_LEKTOR_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete lekture.
Dobijаš PRIJEVOD (sirovi, prije lekture) i LEKTORIRANI TEKST (nakon lekture).
Provjeri da li je lektura POGORŠALA tekst na jedan od ovih načina:
1. Izbrisane su rečenice ili dijelovi sadržaja koji postoje u prijevodu
2. Dodan je sadržaj koji ne postoji u prijevodu (izmišljene rečenice, opisi)
3. Promijenjeni su nazivi likova ili ključni termini
4. Tekst je na engleskom ili sadrži mnogo engleskih riječi umjesto bosanskog/hrvatskog
Ako je lektura ispravna (poboljšala stil, gramatiku, ritam) — vrati ok=true.
Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

# Post-lektor validator thresholds
_PLV_MIN_TEXT_LEN = 40          # minimum chars in sirovi to bother validating
_PLV_MIN_LENGTH_RATIO = 0.80    # rollback if lektorirani is <80% of sirovi
_PLV_MAX_LENGTH_RATIO = 1.30    # rollback if lektorirani is >130% of sirovi
_PLV_MAX_ENGLISH_RATIO = 0.05   # rollback if >5% English words after lektura

_ANALIZA_SYS = """\
Pročitaj priloženi uvodni tekst knjige i ekstraktuj:
1. Žanr i ton (npr: dark fantasy, thriller, romantika, SF, historijski)
2. Stil pripovijedanja (1. lice, 3. lice ograničeno, 3. lice sveznajuće)
3. Period radnje (suvremeni / historijski — koje doba / fantastični / budućnost)
4. Do 10 ključnih likova u formatu "Ime: [opis, M/Ž]"
5. 5-10 specifičnih termina ili argota koji se ponavljaju

Vrati ISKLJUČIVO JSON:
{"zanr":"...","ton":"...","stil_pripovijedanja":"...","period":"...",
 "likovi":{"ImeLika":"opis, M/Ž"},"glosar":{"OrigTerm":"kako prevesti"}}
"""


# ============================================================================
# EPUB TIPOGRAFIJA — POMOĆNE FUNKCIJE
# ============================================================================
def _to_roman(n: int) -> str:
    """Pretvori cijeli broj u rimski broj (I, II, III, IV...)."""
    if n < 1:
        return str(n)
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = ""
    for v, s in vals:
        while n >= v:
            result += s
            n -= v
    return result


# CSS tekstura ostarjelog papira (kodirana, bez slika)
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
    "  font-family: Georgia, 'Palatino Linotype', Palatino, serif;"
    "}"
    "p {"
    "  line-height: 1.85 !important;"
    "  text-indent: 1.8em !important;"
    "  margin-bottom: 0.75em !important;"
    "  font-size: 1.1em !important;"
    "  text-align: justify;"
    "}"
)


def _inject_epub_global_css(soup) -> None:
    """Ubaci globalni CSS (papirna tekstura + tipografija) u <head> dokumenta."""
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


# ============================================================================
# KLASA
# ============================================================================
class SkriptorijAllInOne:
    def __init__(self, book_path, model_name, shared_stats, shared_controls):
        self.book_path = Path(book_path)
        self.model_name = model_name
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls
        self.fleet = FleetManager(config_path="dev_api.json")
        register_active_fleet(self.fleet)

        self.clean_book_name = re.sub(r"[^a-zA-Z0-9_\-]", "", self.book_path.stem)
        self.work_dir = self.book_path.parent / f"_skr_{self.clean_book_name}"
        self.checkpoint_dir = self.work_dir / "checkpoints"
        self.out_path = self.book_path.parent / f"PREVEDENO_{self.clean_book_name}.epub"

        # #11: Kontekst knjige
        self.book_context = {
            "zanr": "nepoznat",
            "ton": "neutralan",
            "stil_pripovijedanja": "3. lice",
            "period": "suvremeni",
            "likovi": {},
            "glosar": {},
        }
        self.knjiga_analizirana = False
        self.glosar_tekst = ""

        self.toc_entries, self.chapter_counter = [], 0
        self.global_total_chunks = self.global_done_chunks = 0
        self.stvarno_prevedeno_u_sesiji = self.spaseno_iz_checkpointa = 0
        self.chunk_skips = 0
        self.html_files = []
        self._last_live_epub_time = 0.0

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"V8 Engine inicijaliziran za: {self.book_path.name}", "tech")

    def log(self, msg, ltype="info", en_text=""):
        add_audit(msg, ltype, en_text, self.shared_stats)

    # #7: Poboljšan atomic write — čisti stari .tmp
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
        # Croatian/Bosnian diacriticals (š, ć, č, ž, đ) are definitive proof of
        # a non-English text — skip the stopword check entirely.
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

    def _get_prevodilac_prompt(self, glosar_chunk="") -> str:
        ton = self.book_context.get("ton", "neutralan")
        stil = self.book_context.get("stil_pripovijedanja", "3. lice")
        zanr = self.book_context.get("zanr", "nepoznat")
        period = self.book_context.get("period", "suvremeni")
        ton_injekcija = (
            f"Žanr: {zanr} | Ton: {ton} | Period: {period} | Narativni stil: {stil}. "
            f"Vokabular i registar prilagodi ovim parametrima — književni jezik, ne novinski."
        )
        return _PREVODILAC_TEMPLATE.format(
            ton_injekcija=ton_injekcija,
            glosar_injekcija=glosar_chunk or self.glosar_tekst or "Nema glosara.",
        )

    def _get_lektor_prompt(self, prev_kraj="", glosar_injekcija="") -> str:
        zanr = self.book_context.get("zanr", "nepoznat")
        ton = self.book_context.get("ton", "neutralan")
        stil = self.book_context.get("stil_pripovijedanja", "3. lice")
        period = self.book_context.get("period", "suvremeni")
        return _LEKTOR_TEMPLATE.format(
            knjiga_kontekst=f"Žanr: {zanr} | Ton: {ton} | Period: {period}",
            stil_injekcija=f"Prilagodi žanru {zanr} ({ton}). Stil: {stil}. Prirodan ritam.",
            prev_kraj=(prev_kraj[-600:] if prev_kraj else "—"),
            glosar_injekcija=glosar_injekcija or "Nema specifičnog glosara.",
        )

    def _get_korektor_prompt(self) -> str:
        return _KOREKTOR_TEMPLATE

    # ============================================================================
    # #9: OVERLAP CHUNKING
    # ============================================================================
    def chunk_html(self, html_content: str, max_words=250) -> list:
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

    # ============================================================================
    # MREŽNI SLOJ — #6 asyncio.to_thread
    # ============================================================================
    async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key):
        try:
            # #3: asyncio.timeout sprječava beskonačno čekanje
            async with asyncio.timeout(120):
                # #6: asyncio.to_thread umjesto deprecated get_event_loop
                resp = await asyncio.to_thread(
                    requests.post,
                    url,
                    headers=headers,
                    json=json_payload,
                    timeout=90,
                    verify=False,
                )
            # #5: Pravi rate-limit podaci iz headera
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                # Pokušaj pročitati retry delay iz response body-a (Gemini API stil)
                body_retry = 0.0
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("error", {}).get("message", "")
                    # Gemini ponekad piše "Retry after Xs" u poruci (cijeli i decimalni)
                    m = re.search(r"retry\s+after\s+([\d.]+)", err_msg, re.IGNORECASE)
                    if m:
                        body_retry = float(m.group(1))
                    # Gemini može vratiti i "retryDelay" u details (npr. "60s" ili "60.5s")
                    for detail in err_body.get("error", {}).get("details", []):
                        rd = detail.get("retryDelay", "")
                        if rd:
                            m2 = re.search(r"([\d.]+)", str(rd))
                            if m2:
                                body_retry = max(body_retry, float(m2.group(1)))
                                break
                except Exception:
                    pass
                backoff = self.fleet.get_backoff_for_provider(prov_upper)
                wait = max(backoff, body_retry, 5.0)
                self.log(
                    f"[{prov_upper}] 429 Rate limit. Čekam {wait:.0f}s ⏳", "warning"
                )
                await asyncio.sleep(wait)
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
                "GROQ":        _url_groq(),
                "CEREBRAS":    _url_cerebras(),
                "SAMBANOVA":   _url_samba(),
                "MISTRAL":     _url_mistral(),
                "OPENROUTER":  _url_openrouter(),
                "GITHUB":      _url_github(),
                "TOGETHER":    _url_together(),
                "FIREWORKS":   _url_fireworks(),
                "CHUTES":      _url_chutes(),
                "HUGGINGFACE": _url_huggingface(),
                "KLUSTER":     _url_kluster(),
            }
            url = url_map.get(prov_upper, _url_groq())
            headers["Authorization"] = f"Bearer {key.strip()}"
            if prov_upper == "CEREBRAS":
                payload["max_completion_tokens"] = payload.pop("max_tokens")

        lock = await _ensure_global_lock()
        async with lock:
            # Adaptive throttle: počni s per-provajder minimumom, pa proširi
            # kad rate-limit headeri signaliziraju niski preostali kapacitet.
            gap = _PROVIDER_MIN_GAP.get(prov_upper, MIN_GAP)
            key_state = self.fleet.fleet.get(prov_upper, {}).get(key)
            if key_state is not None:
                # RPM: ako je < 50 % minutnog kvota preostalo, rasporedi ravnomjernije
                if key_state.rate_limit_minute > 0 and key_state.remaining_minute > 0:
                    if key_state.remaining_minute < key_state.rate_limit_minute * 0.5:
                        safe_rpm_gap = 60.0 / key_state.remaining_minute
                        gap = max(gap, safe_rpm_gap)
                # RPD: ako je < 50 % dnevnog kvota preostalo, linearno povećaj gap
                if key_state.rate_limit_day > 0 and key_state.remaining_day > 0:
                    rpd_ratio = key_state.remaining_day / key_state.rate_limit_day
                    if rpd_ratio < 0.5:
                        rpd_multiplier = 1.0 + (0.5 - rpd_ratio) / 0.5 * 4.0
                        gap = max(gap, _PROVIDER_MIN_GAP.get(prov_upper, MIN_GAP) * rpd_multiplier)

            # Interno RPM praćenje — dopunjuje header-bazirani throttle.
            # Kada API ne vraća rate-limit headere (remaining_minute == -1),
            # ovo je jedini aktivni zaštitni mehanizam. Kad headeri jesu dostupni,
            # može dodatno proširiti gap ako je interno számlálás bliže limitu.
            rpm_used = self.fleet.get_rpm_used(prov_upper, key)
            rpm_limit = self.fleet.get_effective_rpm_limit(prov_upper, key)
            if rpm_limit > 0 and rpm_used >= int(rpm_limit * 0.8):
                # Rasporedi preostale zahtjeve ravnomjerno do kraja minute
                remaining_rpm = max(1, rpm_limit - rpm_used)
                internal_gap = 60.0 / remaining_rpm
                gap = max(gap, internal_gap)

            # Humanizacija: nasumični jitter u rasponu 0.5 – max(1.5, gap*0.3)
            # da spriječimo pravilne impulse koji izgledaju botovski.
            # max(1.5, ...) garantira da drugi argument uvijek > 0.5 (min).
            gap += random.uniform(0.5, max(1.5, gap * 0.3))

            # Ključ je per-provajder (ne per-model) da oba Gemini modela dijele timer
            elapsed = time.time() - _LAST_CALLS.get(prov_upper, 0)
            if elapsed < gap:
                await asyncio.sleep(gap - elapsed)
            _LAST_CALLS[prov_upper] = time.time()
            # Zabilježi zahtjev u interno sliding-window brojilo
            self.fleet.record_request(prov_upper, key)

        data = await self._async_http_post(
            url, headers, payload, prov_upper, prov_upper, key
        )
        if not data:
            return None, None

        # Ekstrakcija odgovora
        if prov_upper == "COHERE" and "message" in data:
            raw = data["message"]["content"][0]["text"].strip()
        elif "choices" in data:
            choice = data["choices"][0] if data["choices"] else {}
            msg = choice.get("message") or {}
            raw = msg.get("content") or ""
            raw = raw.strip()
            if not raw:
                self.log(f"[{prov_upper}] Prazan odgovor (nema 'message'/'content' u choices).", "tech")
                return None, None
        else:
            return None, None

        return raw, f"{prov_upper}—{model}"

    async def _call_ai_engine(
        self, prompt, chunk_idx, uloga="LEKTOR", filename="", sys_override=None
    ):
        svi = list(self.fleet.fleet.keys())

        # #17: Gemini 2.5 flash | #18: Temperature po ulozi
        prioritetni_redosljed = False  # False = shuffle; LEKTOR postavlja na True (fiksni prioritet)
        opt_max_tokens = 2048  # Povećava se za LEKTOR i KOREKTOR
        if uloga == "LEKTOR":
            opt_temp = 0.65  # Viša temperatura = bogatiji, raznovrsniji vokabular
            opt_max_tokens = 4096
            prioritetni_redosljed = True
            # Primarni: Gemini Flash + veliki modeli ostalih provajdera (jakost > brzina)
            # Rezervni: Flash-Lite i mali modeli kao fallback
            primarne = []
            rezervne = []
            # Eksplicitni prioritetni redosljed za primarne: Gemini Flash prvi
            _PRIMARNI_REDOSLJED = [
                "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA",
                "TOGETHER", "FIREWORKS", "CHUTES", "HUGGINGFACE", "KLUSTER",
                "GROQ", "OPENROUTER", "GITHUB",
            ]
            _REZERVNI = ["CEREBRAS"]
            svi_upper = {p.upper() for p in svi}
            for up in _PRIMARNI_REDOSLJED:
                if up not in svi_upper:
                    continue
                if up == "GEMINI":
                    primarne.append(("GEMINI", "gemini-2.5-flash"))
                else:
                    m = self.fleet.get_active_model(up)
                    if m:
                        primarne.append((up, m))
            for p in svi:
                up = p.upper()
                if up == "GEMINI":
                    rezervne.append(("GEMINI", "gemini-2.5-flash-lite-preview-06-17"))
                elif up in _REZERVNI:
                    m = self.fleet.get_active_model(up)
                    if m:
                        rezervne.append((up, m))
            random.shuffle(rezervne)
            pms = primarne + rezervne
            sys_c = sys_override or self._get_lektor_prompt()

        elif uloga == "KOREKTOR":
            # Korektor koristi nisku temperaturu za precizne gramatičke ispravke
            opt_temp = 0.25
            opt_max_tokens = 4096
            pms = []
            for p in svi:
                up = p.upper()
                # Preferiramo brze modele za korektor prolaz
                if up in ["GROQ", "CEREBRAS", "GEMINI"]:
                    m = (
                        "gemini-2.5-flash-lite-preview-06-17"
                        if up == "GEMINI"
                        else self.fleet.get_active_model(up)
                    )
                    if m:
                        pms.append((up, m))
                        break  # Samo jedan motor za korektor
            sys_c = sys_override or self._get_korektor_prompt()

        elif uloga == "PREVODILAC":
            opt_temp = 0.18  # #18: Niska temperatura = precizan prijevod
            pms = []
            for p in svi:
                up = p.upper()
                if up in [
                    "GROQ",
                    "CEREBRAS",
                    "SAMBANOVA",
                    "GEMINI",
                    "MISTRAL",
                    "OPENROUTER",
                    "TOGETHER",
                    "FIREWORKS",
                    "CHUTES",
                    "HUGGINGFACE",
                    "KLUSTER",
                    "GITHUB",
                ]:
                    m = (
                        "gemini-2.5-flash"
                        if up == "GEMINI"
                        else (self.fleet.get_active_model(up) or "default")
                    )
                    pms.append((up, m))
            sys_c = sys_override or self._get_prevodilac_prompt()

        elif uloga == "VALIDATOR":
            opt_temp = 0.05
            pms = []
            for p in svi:
                up = p.upper()
                if up in ["GROQ", "CEREBRAS", "GEMINI"]:
                    m = (
                        "gemini-2.5-flash-lite-preview-06-17"
                        if up == "GEMINI"
                        else self.fleet.get_active_model(up)
                    )
                    pms.append((up, m))
                    break
            sys_c = _VALIDATOR_SYS

        elif uloga == "ANALIZA":
            opt_temp = 0.1
            pms = []
            for p in svi:
                up = p.upper()
                if up in ["GEMINI", "GROQ", "CEREBRAS", "TOGETHER", "FIREWORKS", "CHUTES", "KLUSTER"]:
                    m = (
                        "gemini-2.5-flash"
                        if up == "GEMINI"
                        else self.fleet.get_active_model(up)
                    )
                    pms.append((up, m))
            sys_c = _ANALIZA_SYS
        else:
            return None, "N/A"

        if not prioritetni_redosljed:
            random.shuffle(pms)
        if not pms:
            return None, "N/A"

        for pokusaj in range(5):
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return None, "N/A"
            for prov_upper, model in pms:
                raw, label = await self._call_single_provider(
                    prov_upper, model, sys_c, prompt, opt_temp, max_tokens=opt_max_tokens
                )
                if raw:
                    return raw, label
            # #8: Exponential backoff s jitterom
            wait = min(10 * (2**pokusaj), 120) + random.uniform(0, 3)
            self.log(
                f"[Pokušaj {pokusaj + 1}/5] Motori zauzeti. Čekam {wait:.0f}s ⏳",
                "warning",
            )
            await asyncio.sleep(wait)

        return None, "N/A"

    # ============================================================================
    # #4 + #11: ANALIZA KNJIGE — jednom na početku, rezultat se cachira
    # ============================================================================
    async def analiziraj_knjigu(self, intro_text: str):
        # #4: Provjeri cache najprije
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
                    f"👥 Likovi: {likovi or '—'}",
                    "system",
                )
                return
            except Exception:
                pass  # Oštećen cache — ponovi analizu

        self.shared_stats["status"] = "ANALIZA KNJIGE..."
        self.log("🔬 Analiziram kontekst: žanr, ton, likovi, glosar...", "system")
        clean = BeautifulSoup(intro_text, "html.parser").get_text()[:2500]
        raw, engine = await self._call_ai_engine(clean, 0, uloga="ANALIZA")
        if raw:
            try:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                ctx = json.loads(m.group() if m else raw)
                self.book_context.update(ctx)
                self.knjiga_analizirana = True
                self.glosar_tekst = self._build_glosar_tekst()
                # #4: Spremi u cache
                self._atomic_write(cache_file, json.dumps(self.book_context, ensure_ascii=False, indent=2))
                likovi = ", ".join(list(self.book_context.get("likovi", {}).keys())[:5])
                self.log(
                    f"✅ Analiza završena ({engine})<br>"
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

    # ============================================================================
    # SIROVI PREVOD SPAŠAVAČ — retry lektor kada bi blok završio kao sirovi prevod
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
    ):
        """Pokušaj lekturu na alternativnim provajderima s eskalacijom temperature.

        Poziva se svaki put kad bi blok inače pao na sirovi prijevod (halucinacija,
        engleski ostaci, post-validator rollback). Iterira kroz sve dostupne
        provajdere na četiri razine temperature. Vraća (finalno, label) ili
        (None, None) ako svi pokušaji propadnu — tada pozivač zadrži sirovi.
        """
        TEMP_LADDER = [0.50, 0.70, 0.85, 0.95]
        PROV_REDOSLJED = [
            "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA",
            "TOGETHER", "FIREWORKS", "CHUTES", "HUGGINGFACE", "KLUSTER",
            "GROQ", "CEREBRAS", "OPENROUTER", "GITHUB",
        ]
        svi_upper = {p.upper() for p in self.fleet.fleet.keys()}

        lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar)
        p_lek = (
            f"IZVORNI TEKST (referenca):\n{chunk}\n\n"
            f"TEKST ZA LEKTURU:\n{sirovo}\n\n"
            f"Prethodni pokušaj lekture bio je neprihvatljiv ({razlog}). "
            f"Izvrši kompletnu ponovnu lekturu: ispravi sve greške, "
            f"ukloni engleske ostatke i vrati prirodan bosanski/hrvatski tekst."
        )

        for temp in TEMP_LADDER:
            for up in PROV_REDOSLJED:
                if up not in svi_upper:
                    continue
                if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                    return None, None
                m_name = (
                    "gemini-2.5-flash"
                    if up == "GEMINI"
                    else (self.fleet.get_active_model(up) or "default")
                )
                raw_s, label_s = await self._call_single_provider(
                    up, m_name, lek_sys, p_lek, temp, max_tokens=4096
                )
                if not raw_s:
                    continue
                try:
                    ms = re.search(r"\{.*\}", raw_s, re.DOTALL)
                    obj_s = json.loads(ms.group() if ms else raw_s)
                    kand = _agresivno_cisti(obj_s.get("finalno_polirano", next(iter(obj_s.values()), "")))
                except Exception:
                    kand = _agresivno_cisti(raw_s)

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
            f"[{file_name}] Blok {chunk_idx}: ⛔ Svi rescue pokušaji propalim — zadržavam sirovi.",
            "warning",
        )
        return None, None

    # ============================================================================
    # #14: TROSTEPENI PIPELINE: Prijevod → Validator → Lektor
    # ============================================================================
    async def process_chunk_with_ai(
        self, chunk: str, prev_ctx: str, next_ctx: str, chunk_idx: int, file_name: str
    ) -> tuple:
        chk_fajl = self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"

        if chk_fajl.exists():
            try:
                zapamceno = chk_fajl.read_text("utf-8", errors="ignore")
                if len(zapamceno) > 10 and _detektuj_en_ostatke(zapamceno) < 0.08:
                    # #5: Log kad se blok učita iz cache-a
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

        # ── KORAK 1: PRIJEVOD ───────────────────────────────────────────
        if jezik == "HR":
            sirovo, prov1 = chunk, "AUTO-HR (Bypass)"
            # Safety check: if the bypassed chunk has no Croatian diacriticals
            # AND a notable English word density, warn — it may be untranslated
            # English that slipped through detection.
            cist_chunk = re.sub(r"<[^>]+>", "", chunk)
            if not any(c in _HR_DIACRITICALS for c in cist_chunk):
                en_score = _detektuj_en_ostatke(chunk)
                if en_score > 0.05:
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: ⚠️ HR-bypass na tekstu bez hrv. dijakritika "
                        f"(en_score={en_score:.2f}) — moguć EN propust.",
                        "warning",
                    )
            self.log(f"[{file_name}] Blok {chunk_idx}: HR, preskačem prijevod.", "info")
        else:
            prev_sys = self._get_prevodilac_prompt(glosar_chunk=rel_glosar)
            p_prevod = (
                f"Kontekst prethodnog odlomka:\n{prev_ctx[-300:]}\n\n"
                f"Tekst za prijevod:\n```\n{chunk}\n```"
            )
            raw_p, prov1 = await self._call_ai_engine(
                p_prevod,
                chunk_idx,
                uloga="PREVODILAC",
                filename=file_name,
                sys_override=prev_sys,
            )
            if not raw_p:
                self.chunk_skips += 1
                self.shared_stats["skipped"] = str(self.chunk_skips)
                return None, "N/A"
            sirovo = _agresivno_cisti(raw_p)

        # ── KORAK 2: VALIDATOR (#14) ─────────────────────────────────────
        if jezik != "HR":
            val_prompt = (
                f"ORIGINAL (EN):\n{chunk[:800]}\n\nPRIJEVOD (HR/BS):\n{sirovo[:800]}"
            )
            val_raw, _ = await self._call_ai_engine(
                val_prompt, chunk_idx, uloga="VALIDATOR", filename=file_name
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
                        retry_raw, prov1 = await self._call_ai_engine(
                            retry_p, chunk_idx, uloga="PREVODILAC", filename=file_name
                        )
                        if retry_raw:
                            sirovo = _agresivno_cisti(retry_raw)
                except Exception:
                    pass

        # ── KORAK 3: LEKTOR ──────────────────────────────────────────────
        lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar)
        p_lek = (
            f"IZVORNI TEKST (referenca):\n{chunk}\n\n"
            f"TEKST ZA LEKTURU:\n{sirovo}\n\n"
            f"Izvrši dubinsku lekturu: (a) ispravi kalkirane i doslovno prevedene konstrukcije, "
            f"(b) uskladi glagolska vremena unutar odlomka, "
            f"(c) poboljšaj ritam dijaloga da zvuči prirodno na bosanskom/hrvatskom."
        )
        raw_l, prov2 = await self._call_ai_engine(
            p_lek, chunk_idx, uloga="LEKTOR", filename=file_name, sys_override=lek_sys
        )

        finalno = ""
        if raw_l:
            try:
                m = re.search(r"\{.*\}", raw_l, re.DOTALL)
                obj = json.loads(m.group() if m else raw_l)
                kandidat = obj.get("finalno_polirano", next(iter(obj.values()), ""))
                if not _je_placeholder(kandidat):
                    finalno = kandidat
            except Exception:
                kandidat = _agresivno_cisti(raw_l)
                if not _je_placeholder(kandidat):
                    finalno = kandidat

        # #1: Ako lektor nije vratio ništa (ili placeholder), retry sa drugom temperaturom
        if not finalno:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: Lektor nije odgovorio — retry sa alt. temperaturom.",
                "warning",
            )
            retry_lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar)
            retry_p_lek = (
                f"IZVORNI TEKST (referenca):\n{chunk}\n\n"
                f"TEKST ZA LEKTURU:\n{sirovo}\n\n"
                f"Izvrši dubinsku lekturu: (a) ispravi kalkirane i doslovno prevedene konstrukcije, "
                f"(b) uskladi glagolska vremena unutar odlomka, "
                f"(c) poboljšaj ritam dijaloga da zvuči prirodno na bosanskom/hrvatskom."
            )
            # Retry s višom temperaturom za raznovrsnost — koristi iste prioritetne provajdere
            svi = list(self.fleet.fleet.keys())
            svi_upper = {p.upper() for p in svi}
            pms_retry = []
            for up in ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "GROQ"]:
                if up not in svi_upper:
                    continue
                m_name = (
                    "gemini-2.5-flash"
                    if up == "GEMINI"
                    else (self.fleet.get_active_model(up) or "default")
                )
                pms_retry.append((up, m_name))
            for prov_r, model_r in pms_retry:
                raw_retry, label_r = await self._call_single_provider(
                    prov_r, model_r, retry_lek_sys, retry_p_lek, 0.80, max_tokens=4096
                )
                if raw_retry:
                    try:
                        mr = re.search(r"\{.*\}", raw_retry, re.DOTALL)
                        obj_r = json.loads(mr.group() if mr else raw_retry)
                        kandidat_r = obj_r.get("finalno_polirano", next(iter(obj_r.values()), ""))
                        if not _je_placeholder(kandidat_r):
                            finalno = kandidat_r
                    except Exception:
                        kandidat_r = _agresivno_cisti(raw_retry)
                        if not _je_placeholder(kandidat_r):
                            finalno = kandidat_r
                    if finalno:
                        prov2 = label_r
                        break

        if not finalno:
            finalno, prov2 = sirovo, f"{prov1}(FS)"

        # #15: Finalni prolaz — AI markeri
        finalno = _ocisti_ai_markere(finalno)

        # #8: Final validation — provjera kvalitete prije čuvanja
        finalno_tekst = re.sub(r"<[^>]+>", "", finalno)
        if len(finalno_tekst.strip()) < 20:
            # Tekst premali — odbaci i koristi original
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Rezultat premali ({len(finalno_tekst)} znakova) — koristim original.",
                "warning",
            )
            finalno = chunk
        elif _detektuj_en_ostatke(finalno) > 0.15:
            # Previše engleskog — cleanup
            self.log(
                f"[{file_name}] Blok {chunk_idx}: 🧹 Detektovano >15% engleskog — čistim ostatke.",
                "warning",
            )
            # Pokušaj ukloniti engleski tekst agresivnim čišćenjem
            finalno = _agresivno_cisti(finalno)
            if _detektuj_en_ostatke(finalno) > 0.15:
                # Agresivno čišćenje nije pomoglo — pokušaj rescue lektor
                spas, spas_label = await self._spasi_od_sirovog(
                    sirovo, chunk, chunk_idx, file_name, prev_ctx, rel_glosar,
                    "previše engleskog i nakon čišćenja"
                )
                if spas:
                    finalno = spas
                    prov2 = spas_label
                else:
                    finalno = sirovo  # Fallback na sirovi prijevod ako rescue propadne

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
                spas, spas_label = await self._spasi_od_sirovog(
                    sirovo, chunk, chunk_idx, file_name, prev_ctx, rel_glosar,
                    f"gigantska halucinacija ratio={ratio:.2f}"
                )
                if spas:
                    finalno = spas
                    prov2 = spas_label
                else:
                    finalno = sirovo  # Posljednji fallback
            else:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju (ratio={ratio:.2f}), puštam dalje.",
                    "warning",
                )

        # ── KORAK 3b: POST-LEKTOR VALIDATOR (selektivni) ─────────────────────
        # Pokrenuti samo kad lektura pokazuje sumnjive metrike:
        #   • >20% kraći od sirovog prijevoda (lektor možda izbrisao rečenice)
        #   • >30% duži od sirovog prijevoda (lektor možda dodao sadržaj)
        #   • >5% engleskih riječi u lektoriranom tekstu (regresija na engleski)
        sirovo_len = len(re.sub(r"<[^>]+>", "", sirovo).strip())
        lektorirani_len = len(re.sub(r"<[^>]+>", "", finalno).strip())
        plv_ratio = lektorirani_len / sirovo_len if sirovo_len > 0 else 1.0
        plv_en = _detektuj_en_ostatke(finalno)
        plv_treba = (
            sirovo_len > _PLV_MIN_TEXT_LEN
            and finalno != sirovo
            and (
                plv_ratio < _PLV_MIN_LENGTH_RATIO
                or plv_ratio > _PLV_MAX_LENGTH_RATIO
                or plv_en > _PLV_MAX_ENGLISH_RATIO
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
            plv_raw, _ = await self._call_ai_engine(
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

        # ── KORAK 4: KOREKTOR (print-quality gramatička korektura) ──────────
        # Pokrenuti samo za blokove s dovoljno sadržaja (>80 znakova teksta)
        finalno_tekst_len = len(re.sub(r"<[^>]+>", "", finalno).strip())
        if finalno_tekst_len > 80:
            kor_prompt = (
                f"Tekst za korekturu:\n{finalno}"
            )
            raw_k, prov3 = await self._call_ai_engine(
                kor_prompt, chunk_idx, uloga="KOREKTOR", filename=file_name
            )
            if raw_k:
                try:
                    mk = re.search(r"\{.*\}", raw_k, re.DOTALL)
                    obj_k = json.loads(mk.group() if mk else raw_k)
                    korektura = obj_k.get("korektura", next(iter(obj_k.values()), ""))
                    korektura = _agresivno_cisti(korektura)
                    # Prihvati korektu samo ako nije halucinirala i nije placeholder
                    if (
                        korektura
                        and not _je_placeholder(korektura)
                        and not _detektuj_halucinaciju(finalno, korektura, uloga="LEKTOR")
                    ):
                        finalno = korektura
                        prov2 = f"{prov2}→{prov3}(K)"
                except Exception:
                    pass  # Korektura neuspješna — zadrži lektor verziju

        # ── KORAK 5: TIPOGRAFIJA — deterministička B/H/S pravila ────────────
        finalno = _post_process_tipografija(finalno)

        self._atomic_write(chk_fajl, finalno)
        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        # #2: Ažuriraj shared_stats za /api/status endpoint
        self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji
        self.shared_stats["spaseno_iz_checkpointa"] = self.spaseno_iz_checkpointa

        aud = (
            f"<div style='border-left:4px solid #0ea5e9; background:#0f172a; "
            f"padding:10px; margin:4px 0; border-radius:4px;'>"
            f"<div style='font-size:0.75em; color:#94a3b8; margin-bottom:4px;'>"
            f"📦 Blok {chunk_idx} | {prov1} → {prov2}</div>"
            f"<div style='display:grid; grid-template-columns:1fr 1fr; gap:8px; "
            f"font-size:0.82em; font-family:monospace;'>"
            f"<div style='color:#64748b;'>EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:70]}…</div>"
            f"<div style='color:#e2e8f0;'>HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:70]}…</div>"
            f"</div></div>"
        )

        self.log("", "accordion", en_text=aud)
        return finalno, f"{prov1}→{prov2}"

    async def process_single_file_worker(self, file_path):
        file_name = file_path.name
        try:
            raw_html = file_path.read_text("utf-8", errors="ignore")
        except Exception:
            return

        chunks = self.chunk_html(raw_html, max_words=250)
        if not chunks:
            return

        # Parsuj original da bismo sačuvali <head> i strukturu dokumenta
        orig_soup = BeautifulSoup(raw_html, "html.parser")

        self.shared_stats["current_file"] = file_name
        self.shared_stats["total_file_chunks"] = len(chunks)
        final_parts = []

        for i, chunk in enumerate(chunks):
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return

            while self.shared_controls.get("pause"):
                await asyncio.sleep(1)

            p_ctx, n_ctx = self.get_context_window(chunks, i, file_name)
            res, eng = await self.process_chunk_with_ai(
                chunk, p_ctx, n_ctx, i, file_name
            )
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
                self.shared_stats["current_file_idx"] = (
                    self.html_files.index(file_path) + 1
                )
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

        # Upiši prevedeni sadržaj natrag u fajl, čuvajući <head> i strukturu dokumenta
        body = orig_soup.body
        if body:
            body.clear()
            translated_soup = BeautifulSoup("".join(final_parts), "html.parser")
            for child in list(translated_soup.children):
                body.append(child.extract())
            file_path.write_text(str(orig_soup), encoding="utf-8")
        else:
            # Fallback: nema <body> taga — upiši direktno
            file_path.write_text("".join(final_parts), encoding="utf-8")

    # ============================================================================
    # OBLIKOVANJE + NCX + FINALIZACIJA
    # ============================================================================
    def buildlive_epub(self):
        try:
            live_epub = self.book_path.parent / f"(LIVE)_{self.clean_book_name}.epub"
            # Reset brojača poglavlja za ovaj prolaz live EPUB-a
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
        """Primijeni dropcap, romanizovana poglavlja, ukrase i dodaj u TOC."""
        needs_dropcap = True

        # Ubaci globalni CSS (papirna tekstura) u <head>
        _inject_epub_global_css(soup)

        # ════════════════════════════════════════════════════════════
        # PETLJA 1: Zaglavlja (h1, h2, h3) — Romanizacija + Ukrasi
        # ════════════════════════════════════════════════════════════
        for heading in soup.find_all(["h1", "h2", "h3"]):
            t = heading.get_text(strip=True)

            # Preskoči ako je naslov prazan, sadrži "ZADATAK:" ili je predugačak
            if not t or "ZADATAK:" in t.upper() or len(t) > 100:
                heading.name = "p"
                continue

            # Odredi broj poglavlja
            if samo_dropcap:
                self._live_chapter_idx = getattr(self, "_live_chapter_idx", 0) + 1
                chap_num = self._live_chapter_idx
                tid = f"live_ch_{chap_num}_{random.randint(1000, 9999)}"
            else:
                self.chapter_counter += 1
                chap_num = self.chapter_counter
                tid = f"skr_ch_{chap_num}"
                self.toc_entries.append({
                    "title": t,
                    "abs_path": str(html_file),
                    "anchor": tid,
                })

            roman = _to_roman(chap_num)

            # Omotač koji drži cijelo zaglavlje (prisilni prijelom stranice na vrhu)
            wrapper = soup.new_tag("div", attrs={"style": (
                "page-break-before:always; text-align:center; "
                "padding-top:15vh; margin-bottom:4vh;"
            )})
            heading.wrap(wrapper)

            # Rimski broj iznad naslova
            roman_el = soup.new_tag("div", attrs={"style": (
                "font-family:Georgia,'Palatino Linotype',Palatino,serif; "
                "font-size:0.9em; color:#8b0000; letter-spacing:0.55em; "
                "text-transform:uppercase; margin-bottom:0.55em;"
            )})
            roman_el.string = f"\u2014 {roman} \u2014"
            heading.insert_before(roman_el)

            # Gornji ukras iznad naslova (iznad rimskog broja)
            top_orn = soup.new_tag("div", attrs={"style": (
                "color:#8b0000; font-size:1.1em; letter-spacing:0.4em; "
                "margin-bottom:0.4em; opacity:0.75;"
            )})
            top_orn.string = "\u2767 \u2726 \u2767"
            roman_el.insert_before(top_orn)

            # Stil samog naslova
            heading["style"] = (
                "text-align:center; "
                "font-family:Georgia,'Palatino Linotype',Palatino,serif; "
                "font-size:1.9em; font-weight:bold; text-transform:uppercase; "
                "letter-spacing:0.13em; color:#2c1810; margin-bottom:0.5em;"
            )
            heading["id"] = tid

            # Donji ukras ispod naslova
            bot_orn = soup.new_tag("div", attrs={"style": (
                "color:#8b0000; font-size:0.95em; letter-spacing:0.4em; "
                "margin-top:0.6em; opacity:0.75;"
            )})
            bot_orn.string = "\u2726 \u2726 \u2726"
            heading.insert_after(bot_orn)

            needs_dropcap = True

        # ════════════════════════════════════════════════════════════
        # PETLJA 2: Paragrafi — Dodaj dropcap na prvi paragraf
        # ════════════════════════════════════════════════════════════
        for p in soup.find_all("p"):
            if not needs_dropcap:
                break

            if len(p.get_text(strip=True)) > 40:
                # Pronađi prvi NavigableString čvor sa tekstom
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

                    # Kreiraj dropcap span — dekorativni serif font, tamnocrvena boja
                    s = soup.new_tag(
                        "span",
                        attrs={
                            "style": (
                                "float:left; font-size:3.8em; line-height:0.8; "
                                "margin-right:0.08em; margin-bottom:0.05em; "
                                "font-family:Georgia,'Palatino Linotype',Palatino,serif; "
                                "font-weight:bold; color:#8b0000;"
                            )
                        },
                    )

                    # Ako počinje navodnicima, uzmi 2 znaka
                    o = 2 if c[0] in ["'", '"', "\u201e", "\u201c"] else 1
                    s.string = c[:o]
                    node.replace_with(c[o:])
                    p.insert(0, s)
                    needs_dropcap = False

    def generate_ncx(self):
        """Generiši NCX (Table of Contents) za EPUB."""
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
                if (
                    f.is_file()
                    and f.name != "mimetype"
                    and "checkpoints" not in f.parts
                ):
                    z.write(
                        f,
                        f.relative_to(self.work_dir),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
        self.shared_stats.update({"status": "✅ Operacija završena", "pct": 100, "output_file": self.out_path.name})
        self.log(f"📖 EPUB: {self.out_path.name}", "system")


# ============================================================================
# #19: RETROAKTIVNO ČIŠĆENJE CHECKPOINT FAJLOVA
# ============================================================================
def _retroaktivno_cisti_chk_fajlove(checkpoint_dir: Path, log_fn=None) -> int:
    """Skenira sve .chk fajlove i uklanja JSON omotače koje AI ponekad vraća.

    Pokreće se pri svakom lansiranju prije obrade, kako bi stari zagađeni
    blokovi bili automatski popravljeni. Vraća broj popravljenih fajlova.
    """
    if not checkpoint_dir.exists():
        return 0
    popravljeno = 0
    for chk in checkpoint_dir.glob("*.chk"):
        try:
            sadrzaj = chk.read_text("utf-8", errors="ignore")
            ocisceno = _cisti_json_wrapper(sadrzaj.strip())
            if ocisceno != sadrzaj.strip():
                # Upiši popravljenu verziju (atomski: tmp → replace)
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
                        log_fn(f"⚠️ CHK sanacija neuspješna ({chk.name}): {e}", "warning")
        except Exception:
            continue
    if popravljeno and log_fn:
        log_fn(f"✅ Retroaktivna CHK sanacija: {popravljeno} fajl(ov)a popravljeno.", "system")
    return popravljeno


# CSS atributi koji nose boje/fontove hardkodirane u inline styleu
_INLINE_COLOUR_PROPS = re.compile(
    r'\b(?:color|background(?:-color)?|font-(?:color|size)|text-decoration-color)\s*:[^;"}]+[;]?',
    re.IGNORECASE,
)


def _ukloni_inline_stilove(html_fajlovi: list, log_fn=None) -> int:
    """Ukloni inline style atribute koji sadrže boje ili fontove iz epub HTML fajlova.

    Čisti color, background-color i sl. iz style="" atributa.
    Ako style ostane prazan nakon čišćenja, atribut se u potpunosti ukloni.
    Vraća broj modificiranih fajlova.
    """
    modificirano = 0
    for fajl in html_fajlovi:
        try:
            original = fajl.read_text("utf-8", errors="ignore")
            if 'style=' not in original:
                continue
            parser = "xml" if fajl.suffix.lower() in {".xhtml", ".xml"} else "html.parser"
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


def start_skriptorij_from_master(bookpathstr, modelname, sharedstats, shared_controls):
    engine = SkriptorijAllInOne(bookpathstr, modelname, sharedstats, shared_controls)
    engine.log("🚀 V8 Omni-Core pokrenут...", "system")

    engine.work_dir.mkdir(parents=True, exist_ok=True)
    engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # #19: Retroaktivno očisti stare .chk fajlove od JSON omotača
    _retroaktivno_cisti_chk_fajlove(engine.checkpoint_dir, log_fn=engine.log)

    # MOBI podrška — konverzija u EPUB/HTML prije obrade
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
            engine.log("MOBI uspješno konvertovan. Nastavljam V8 obradu.", "system")
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

    # Ukloni inline colour/style atribute iz raspakovanih HTML fajlova.
    # Originalni epub može imati hardkodirane style="color:red" i sl. koje
    # nisu dio CSS fajla — uklanjamo ih da ne zagade izlazni epub.
    _ukloni_inline_stilove(engine.html_files, engine.log)

    for f in engine.html_files:
        try:
            engine.global_total_chunks += len(
                engine.chunk_html(f.read_text("utf-8", errors="ignore"))
            )
        except Exception:
            pass

    async def main_loop():
        # #11: Analiza knjige
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
