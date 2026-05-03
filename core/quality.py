# core/quality.py
"""
Quality scoring engine za Skriptorij / Booklyfi.
Ocjenjuje prevedene blokove na skali 1–10 s detaljnim razlozima.

VERZIJA 2.0 — Realni sistem ocjenjivanja:
  - Diferencirani kriteriji za PREVOD, LEKTURU i RELEKTURU
  - AI scorer dobiva konkretan rubrik umjesto slobodnog ocjenjivanja
  - Fallback nikad ne vraća None — uvijek vraća realnu heurističku ocjenu
  - Posebna provjera: isti tekst prije/poslije relekture → penalizacija
  - Kompozitni score: heuristika (40%) + AI ocjena (60%)
"""
import re
import json
import hashlib
from bs4 import BeautifulSoup

# ─── Konstante ────────────────────────────────────────────────────────────────

_QUALITY_RESCUE_THRESHOLD    = 6.5
_QUALITY_EXCELLENT_THRESHOLD = 8.5

# Težine za EN kontaminaciju
_EN_CONTAMINATION_WEIGHTS = {
    "critical": 0.0,   # >20% engleskog → odmah 1–2
    "high":     2.5,   # 10–20%
    "medium":   4.5,   # 5–10%
    "low":      6.5,   # 2–5%
}

# ─── Pomoćne funkcije ─────────────────────────────────────────────────────────

def _strip_ai_json(text: str) -> str:
    """Uklanja ```json ... ``` ili ``` ... ``` wrappers iz AI odgovora."""
    if not text:
        return text
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*```\s*$', '', t)
    return t.strip()


def _ekstrahuj_cist_tekst(tekst: str) -> str:
    """
    Pouzdano ekstrahuje čist tekst iz HTML-a, JSON-a ili plain texta.
    """
    if not tekst:
        return ""

    # 1. JSON format (.chk fajlovi)
    if tekst.strip().startswith("{"):
        try:
            data = json.loads(_strip_ai_json(tekst))
            for key in ("text", "content", "translated", "html", "tekst"):
                if key in data and isinstance(data[key], str) and data[key].strip():
                    tekst = data[key]
                    break
        except Exception:
            pass

    # 2. HTML ekstrakcija
    for parser in ("lxml", "html.parser"):
        try:
            soup = BeautifulSoup(tekst, parser)
            cist = soup.get_text(separator=" ", strip=True)
            if cist.strip():
                return cist
        except Exception:
            continue

    # 3. Regex fallback
    cist = re.sub(r"<[^>]+>", " ", tekst)
    return " ".join(cist.split())


def _izracunaj_heuristicki_score(tekst: str) -> tuple[float, list[str]]:
    """
    Heuristički pre-score koji ne troši API pozive.
    Vraća (ocjena: float 1.0–10.0, razlozi: list[str]).
    Uvijek vraća konkretnu ocjenu — nikad None.
    """
    from core.text_utils import _detektuj_en_ostatke

    cist = _ekstrahuj_cist_tekst(tekst)
    razlozi = []
    kazne = 0.0  # ukupna kazna oduzima od baze 10.0

    # ── 1. Dužina teksta ────────────────────────────────────────────────────
    if len(cist.strip()) < 20:
        return 1.0, ["Tekst prazan ili prekratak"]
    if len(cist.strip()) < 50:
        kazne += 2.0
        razlozi.append("Vrlo kratak blok")

    # ── 2. Engleski ostatci ─────────────────────────────────────────────────
    en_udio = _detektuj_en_ostatke(cist)
    # Kratki blokovi (<120 znakova) su cesto naslovi, citati, vlastita imena —
    # ne tretiramo ih kao neprevedene bez obzira na EN udio
    _je_kratak_blok = len(cist.strip()) < 120
    if en_udio > 0.25 and not _je_kratak_blok:
        return 1.0, [f"Neprevedeno: {en_udio:.0%} engleskog teksta"]
    elif en_udio > 0.15:
        kazne += 5.0
        razlozi.append(f"Kritična EN kontaminacija: {en_udio:.0%}")
    elif en_udio > 0.08:
        kazne += 3.0
        razlozi.append(f"Visok EN ostatak: {en_udio:.0%}")
    elif en_udio > 0.03:
        kazne += 1.5
        razlozi.append(f"Blagi EN ostatak: {en_udio:.0%}")

    # ── 3. Kalkovi i loše konstrukcije ──────────────────────────────────────
    KALKOVI = [
        # Srpski kalkovi
        (r"\bbio je u stanju da\b",        0.8, "kalk: 'bio je u stanju da'"),
        (r"\bnije bio u mogu[ćc]nosti\b",  0.8, "kalk: 'nije bio u mogućnosti'"),
        (r"\buspio je da uradi\b",          0.8, "kalk: 'uspio je da uradi'"),
        (r"\bpokušao je da\b",              0.3, "kalk: 'pokušao je da'"),
        (r"\bu pogledu toga\b",             0.2, "kalk: 'u pogledu toga'"),
        (r"\bod strane\s+\w+a\b",          0.4, "kalk: 'od strane X-a'"),
        (r"\bpo pitanju\s+",               0.2, "kalk: 'po pitanju'"),
        (r"\bu odnosu na to\b",            0.2, "kalk: 'u odnosu na to'"),
        (r"\bkoristeći se\b",              0.2, "kalk: 'koristeći se'"),
        (r"\bna taj način\b",              0.1, "kalk: 'na taj način'"),
        (r"\bimati u vidu\b",              0.2, "kalk: 'imati u vidu'"),
        (r"\buzeti u obzir to da\b",       0.2, "kalk: 'uzeti u obzir to da'"),
        # Engleski ostaci u tekstu
        (r"\bin order to\b",               2.0, "eng: 'in order to'"),
        (r"\bnevertheless\b",              2.0, "eng: 'nevertheless'"),
        (r"\bhowever\b",                   2.0, "eng: 'however'"),
        (r"\bmoreover\b",                  2.0, "eng: 'moreover'"),
        (r"\bfurthermore\b",              2.0, "eng: 'furthermore'"),
        (r"\bconsequently\b",             2.0, "eng: 'consequently'"),
    ]
    text_lower = cist.lower()
    pronadeni_kalkovi = []
    for pattern, kazna, opis in KALKOVI:
        if re.search(pattern, text_lower):
            kazne += kazna
            pronadeni_kalkovi.append(opis)
    if pronadeni_kalkovi:
        razlozi.append(f"Kalkovi: {', '.join(pronadeni_kalkovi[:3])}")

    # ── 4. Dijalog bez em-crtice ─────────────────────────────────────────────
    # FIX 6: broji tipografske navodnike “”„ zajedno s ASCII "
    navodnici = (cist.count('"')
                 + cist.count('“') + cist.count('”')
                 + cist.count('„') + cist.count('‘') + cist.count('’'))
    em_crtice = cist.count('—')
    dijalog_glagoli = any(g in text_lower for g in [
        "reče", "rekla", "rekao", "upita", "odgovori", "viknu",
        "šapnu", "nastavi", "doda", "uzviknu", "prošaputa", "promrmlja",
    ])
    if navodnici >= 4 and em_crtice == 0 and dijalog_glagoli:
        kazne += 1.5
        razlozi.append("Dijalog s navodnicima umjesto em-crtica")
    elif navodnici >= 6 and em_crtice == 0:
        kazne += 1.0
        razlozi.append("Mogući dijalog bez em-crtica")

    # ── 5. Ponavljanje — isti tekst višestruko ────────────────────────────────
    rijeci = cist.split()
    if len(rijeci) > 20:
        # Provjeri da li se iste fraze ponavljaju više od 3 puta (halucinacija)
        trigrami = [" ".join(rijeci[i:i+3]) for i in range(len(rijeci)-2)]
        max_ponavljanje = max((trigrami.count(t) for t in set(trigrami)), default=0)
        if max_ponavljanje > 4:
            kazne += 3.0
            razlozi.append(f"Ponavljanje fraza ({max_ponavljanje}×)")
        elif max_ponavljanje > 2:
            kazne += 1.0
            razlozi.append("Blago ponavljanje fraza")

    # ── 6. Neprevedeni naslovi / meta ────────────────────────────────────────
    if re.search(r"^(Chapter|Part|Section)\s+\d+", cist.strip(), re.IGNORECASE):
        kazne += 1.5
        razlozi.append("Neprevedeni naslov poglavlja")

    # ── 7. Interpunkcija ─────────────────────────────────────────────────────
    # Dvostruki razmaci, višestruke tačke, itd.
    if re.search(r"  +", cist):
        kazne += 0.3
    if re.search(r"\.{4,}", cist):
        kazne += 0.4
        razlozi.append("Višestruke tačke (elipsa?)")

    # ── Finalna ocjena ───────────────────────────────────────────────────────
    ocjena = max(1.0, min(10.0, 9.2 - kazne))

    if not razlozi and ocjena >= 7.5:
        razlozi.append("Bez heurističkih problema")

    return round(ocjena, 1), razlozi


def _provjeri_nepromjenjenost(stari_tekst: str, novi_tekst: str) -> float:
    """
    Vraća udio sličnosti između starog i novog teksta (0.0–1.0).
    Koristi se za penalizaciju relekture koja ništa nije promijenila.
    """
    stari_hash = _ekstrahuj_cist_tekst(stari_tekst).strip()
    novi_hash  = _ekstrahuj_cist_tekst(novi_tekst).strip()

    if not stari_hash or not novi_hash:
        return 0.0

    # Poređenje na razini karaktera (Jaccard na bigramima)
    def bigrami(s):
        return set(s[i:i+2] for i in range(len(s)-1))

    b1, b2 = bigrami(stari_hash), bigrami(novi_hash)
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


# ─── Glavni AI scorer ─────────────────────────────────────────────────────────

_SCORING_RUBRIC = """
Ocjeni kvalitetu prijevoda na bosanski/hrvatski koristeći OVAJ RUBRIK:

KRITERIJI (svaki od 0–10 bodova, prosječna ocjena je finalna):

1. TAČNOST PREVODA (0–10)
   - 9–10: Savršeno prenosi značenje i nijanse originala
   - 7–8: Blago odstupanje u nijansama, bez gubitka smisla
   - 5–6: Neke greške u značenju, ali razumljivo
   - 3–4: Značajni propusti u prenošenju smisla
   - 1–2: Pogrešno ili neprevedeno

2. JEZIČNI STANDARD BS/HR (0–10)
   - 9–10: Idiomatski besprijekoran bosanski/hrvatski
   - 7–8: Nekoliko blagih kalkova ili stranih fraza
   - 5–6: Više kalkova, srpskih konstrukcija ili engl. ostataka
   - 3–4: Dominiraju kalkovi i loše konstrukcije
   - 1–2: Pretežno engleski ili nečitljivo

3. STIL I ČITLJIVOST (0–10)
   - 9–10: Tečan, književni stil, prirodan ritam
   - 7–8: Uglavnom tečan, mali stilski problemi
   - 5–6: Vidljiv prevodilački trag, awkward mjesta
   - 3–4: Trom, mehaničan stil
   - 1–2: Nečitljivo ili nesuvišlo

4. TIPOGRAFIJA I FORMAT (0–10)
   - 9–10: Em-crtice za dijalog, ispravna interpunkcija
   - 7–8: 1–2 tipografske greške
   - 5–6: Dijalog s navodnicima umjesto crtice, itd.
   - 3–4: Više tipografskih problema
   - 1–2: Potpuno neuređena tipografija

Vrati ISKLJUČIVO JSON bez objašnjenja:
{"ocjena": <prosjek 1–10 s jednom decimalom>, "kriteriji": {"tacnost": <0-10>, "jezik": <0-10>, "stil": <0-10>, "tipografija": <0-10>}, "razlog": "<jedna rečenica o ključnom problemu ili pohvali>"}
"""


async def _scoruj_kvalitetu(
    tekst: str,
    engine_fn,
    chunk_idx: int,
    file_name: str,
    self_obj=None,
    stari_tekst: str = None,
    tip_ocjenjivanja: str = "opci"
) -> float:
    """
    Ocjenjuje kvalitetu teksta — kombinacija heuristike i AI ocjene.
    Nikad ne vraća None — uvijek vraća float 1.0–10.0.
    """

    # ── 1. Heuristički pass ──────────────────────────────────────────────────
    heur_score, heur_razlozi = _izracunaj_heuristicki_score(tekst)

    if heur_score <= 2.0:
        return heur_score

    # ── 2. Provjera nepromjenjenosti (samo za relekturu) ─────────────────────
    relektura_kazna = 0.0
    if stari_tekst is not None and tip_ocjenjivanja == "relektura":
        slicnost = _provjeri_nepromjenjenost(stari_tekst, tekst)
        if slicnost > 0.97:
            relektura_kazna = 2.0
        elif slicnost > 0.90:
            relektura_kazna = 0.8

    # ── 3. AI pass ───────────────────────────────────────────────────────────
    ai_score = None
    try:
        cist = _ekstrahuj_cist_tekst(tekst)
        cist = cist[:900]

        tip_prefix = {
            "prevod":    "TIP: PRIJEVOD (EN->BS/HR). Ocjeni sva 4 kriterija.\n",
            "lektura":   "TIP: RELEKTURA (BS/HR->BS/HR). Ocjeni jezik/stil/tipografiju BEZ tacnosti.\n",
            "relektura": "TIP: RELEKTURA (BS/HR->BS/HR). Ocjeni jezik/stil/tipografiju BEZ tacnosti.\n",
            "opci":      "TIP: OPCI. Ocjeni sva 4 kriterija.\n",
        }.get(tip_ocjenjivanja, "TIP: OPCI.\n")

        prompt = f"{tip_prefix}TEKST ZA OCJENU:\n{cist}"

        # uloga="SCORER" → automatski koristi QUALITY_SCORER_SYS,
        # temp=0.05, max_tokens=128, priority=GROQ/CEREBRAS/GEMINI
        if self_obj is not None:
            raw, _ = await self_obj._call_ai_engine(
                prompt, chunk_idx, uloga="SCORER", filename=file_name
            )
        elif engine_fn is not None:
            raw, _ = await engine_fn(
                prompt, chunk_idx, uloga="SCORER", filename=file_name
            )
        else:
            raw = None

        if raw:
            # Pokušaj 1: jednolinijski JSON
            m = re.search(r"\{[^{}]+\}", raw)
            # Pokušaj 2: višelinijski fallback
            if not m:
                m = re.search(r"\{.*?\}", raw, re.DOTALL)
            if m:
                try:
                    obj = json.loads(_strip_ai_json(m.group()))
                    raw_score = float(obj.get("ocjena", 0))
                    if 1.0 <= raw_score <= 10.0:
                        ai_score = raw_score
                        # Debug: logiramo sumnjive "srednje" ocjene
                        if 5.0 <= raw_score <= 5.9 and self_obj is not None and hasattr(self_obj, "log"):
                            self_obj.log(
                                f"[scorer] ⚠️ Blok {chunk_idx}: AI vratio {raw_score} "
                                f"(srednja zona — provjeri provider i rubrik)",
                                "tech"
                            )
                    else:
                        kriteriji = obj.get("kriteriji", {})
                        if kriteriji:
                            vrijednosti = [v for v in kriteriji.values()
                                           if isinstance(v, (int, float))]
                            if vrijednosti:
                                ai_score = round(sum(vrijednosti) / len(vrijednosti), 1)
                except (json.JSONDecodeError, ValueError):
                    pass

    except Exception as _scorer_exc:
        if self_obj is not None and hasattr(self_obj, "log"):
            self_obj.log(
                f"[scorer] AI ocjena nije dostupna za blok {chunk_idx}: "
                f"{str(_scorer_exc)[:80]}",
                "tech"
            )

    # ── 4. Kompozitni score ───────────────────────────────────────────────────
    if ai_score is not None:
        kompozitni = round(heur_score * 0.35 + ai_score * 0.65, 1)
    else:
        # Bez AI potvrde — konzervativniji (ne kažnjavamo previše, samo nismo sigurni)
        kompozitni = round(heur_score * 0.85, 1)

    kompozitni -= relektura_kazna
    return round(max(1.0, min(10.0, kompozitni)), 1)

async def _scoruj_batch(
    blokovi: list[tuple[str, str, int]],  # (tekst, file_name, chunk_idx)
    engine_fn,
    self_obj=None,
    tip_ocjenjivanja: str = "opci",
) -> dict[str, float]:
    """
    Scoruje više blokova odjednom.
    Vraća {stem: ocjena} dict. Nikad ne vraća None za pojedine blokove.
    """
    import asyncio
    results = {}
    tasks = []
    keys = []
    for tekst, file_name, chunk_idx in blokovi:
        stem = f"{file_name}_blok_{chunk_idx:04d}"
        tasks.append(
            _scoruj_kvalitetu(tekst, engine_fn, chunk_idx, file_name,
                              self_obj=self_obj, tip_ocjenjivanja=tip_ocjenjivanja)
        )
        keys.append(stem)

    scores = await asyncio.gather(*tasks, return_exceptions=True)
    for key, score in zip(keys, scores):
        if isinstance(score, Exception) or score is None:
            # Konzistentan fallback — heuristika za neuspjele
            results[key] = 6.0
        else:
            results[key] = float(score)
    return results


# ─── Summary statistika ───────────────────────────────────────────────────────

def quality_summary(scores: dict) -> dict:
    """
    Generiše summary statistiku iz quality scores dict-a.
    Prihvata i {stem: float} i {stem: {"score": float, ...}} formate.
    Vraća None za avg/min/max kad nema podataka.
    """
    # Normalizacija — prihvati i float i dict format
    normalized = {}
    for k, v in scores.items():
        if isinstance(v, (int, float)):
            normalized[k] = float(v)
        elif isinstance(v, dict) and "score" in v:
            normalized[k] = float(v["score"])

    if not normalized:
        return {
            "avg": None,
            "min": None,
            "max": None,
            "total": 0,
            "excellent": 0,
            "good": 0,
            "poor": 0,
            "critical": 0,
            "pct_print_ready": 0.0,
            "has_data": False,
        }

    vals = list(normalized.values())
    n = len(vals)
    excellent = sum(1 for v in vals if v >= _QUALITY_EXCELLENT_THRESHOLD)
    good      = sum(1 for v in vals if _QUALITY_RESCUE_THRESHOLD <= v < _QUALITY_EXCELLENT_THRESHOLD)
    poor      = sum(1 for v in vals if 4.0 <= v < _QUALITY_RESCUE_THRESHOLD)
    critical  = sum(1 for v in vals if v < 4.0)

    return {
        "avg": round(sum(vals) / n, 2),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "total": n,
        "excellent": excellent,        # ≥8.5 — print-ready
        "good": good,                  # 6.5–8.5 — solidno
        "poor": poor,                  # 4.0–6.5 — treba retro
        "critical": critical,          # <4.0 — kritično
        "pct_print_ready": round((excellent / n) * 100, 1),
        "has_data": True,
    }