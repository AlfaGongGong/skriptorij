# core/text_utils.py
#
# BUGFIX:
#   B02: _detektuj_en_ostatke — vraćala 0.0 za SVE tekstove koji imaju ikoji
#        HR dijakritički znak, čak i ako je 90% tekst engleski.
#        Ispravka: HR dijakritici smanjuju EN score ali ga ne nulliraju.
#   B07: _automatska_korekcija — regex operisao na HTML-u pa propuštao
#        matcheve u "bio je u stanju da<br> uradi". Sada strip HTML tagova.
#        Dodano još kalkova koji su bili propušteni.
#   B19: _strip_ai_json broken regex `r"?` ``` `\s*$"` — fixed u svim fajlovima
#        gdje se pojavljuje (ovdje je _smart_extract).

import re
import json
from bs4 import BeautifulSoup

# FIX: Strane riječi koje EN detektor NE smije brojati kao engleski ostatak
_STRANI_JEZIK_WHITELIST = frozenset({
    # Njemački (čest u književnim prijevodima)
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
    "und", "oder", "nicht", "mit", "von", "bei", "nach", "aus", "auf",
    "ist", "war", "hat", "haben", "sein", "sind", "wird", "wurde",
    "ich", "du", "er", "wir", "ihr", "mich", "mein", "lassen",
    "schlemmen", "nacht", "mann", "herr", "gut", "verdammte",
    # Latinski
    "et", "ad", "per", "sub", "pro", "de", "ex",
    # Talijanski/Španski
    "el", "los", "del", "una",
})

_HR_DIACRITICALS = frozenset("šćčžđŠĆČŽĐ")


def _smart_extract(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)  # B19 FIX: bio r"?```\s*$"
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            # B01 FIX: "finalno_polirano" je prvi — to je što LEKTOR_TEMPLATE vraća
            for k in ["finalno_polirano", "korektura", "translated", "tekst", "text"]:
                if k in data and data[k]:
                    return str(data[k]).strip()
    except Exception:
        pass
    m = re.search(r'"finalno_polirano"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if m:
        return m.group(1)
    return _agresivno_cisti(raw)


def _agresivno_cisti(tekst: str) -> str:
    if not tekst:
        return ""
    tekst = re.sub(r"```.*?```", "", tekst, flags=re.DOTALL)
    tekst = re.sub(r"<OVDJE_IDI_[A-Z_]+>", "", tekst)
    return _ocisti_ai_markere(tekst.strip())


def _ocisti_ai_markere(tekst: str) -> str:
    for p in [
        r"\bNaravno[,!]?\b",
        r"\bSvakako[,!]?\b",
        r"Evo (?:rezultata|prijevoda)",
        r"Izvolite",
    ]:
        tekst = re.sub(p, "", tekst, flags=re.IGNORECASE)
    return tekst.strip()


def _je_placeholder(tekst: str) -> bool:
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    return cist in {"lektorisani tekst ovdje", "korigirani tekst ovdje"}


_EN_STOPWORDS = frozenset({
    "the", "and", "was", "for", "with", "his", "they",
    "have", "from", "this", "that", "are", "not", "but",
    "had", "her", "she", "him", "been", "when", "into",
    "there", "then", "than", "would", "could", "their",
})


def _detektuj_en_ostatke(tekst: str) -> float:
    """
    B02 FIX — Stara verzija vraćala 0.0 za SVE tekstove s ikim HR dijakritičkim
    znakom. To znači da blok "the big house. Kuća. the car. the man. č" nikad
    nije triggerovao rescue (0.0 < 0.08 → ok). Sada: HR dijakritici smanjuju
    score ali ne nulliraju ga — HR tekst normalno dobija nizak score jer ima
    malo EN stop-word, mješani tekst dobija proporcionalan score.
    """
    try:
        cist = re.sub(r"<[^>]+>", "", tekst).lower()
        words = re.findall(r"\b[a-z]{2,}\b", cist)
        if not words:
            return 0.0

        # Broj HR dijakritičkih znakova smanjuje EN signal
        hr_chars = sum(1 for c in cist if c in _HR_DIACRITICALS)
        hr_ratio = hr_chars / max(1, len(cist))

        en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
        raw_en_ratio = en_hits / len(words)

        # Ako ima izrazite HR dijakritike (>0.5% teksta), smanji EN score
        # ali ne nulliraj. 0.005 HR ratio → 50% penalty na EN score.
        if hr_ratio > 0.005:
            damping = max(0.0, 1.0 - (hr_ratio / 0.01))
            return round(raw_en_ratio * damping, 4)

        return round(raw_en_ratio, 4)

    except Exception:
        return 0.0


def _detektuj_halucinaciju(original: str, prijevod: str, uloga: str = "LEKTOR") -> bool:
    try:
        orig_len = len(re.sub(r"<[^>]+>", "", original).strip())
        prev_len = len(re.sub(r"<[^>]+>", "", prijevod).strip())
        if orig_len == 0 or prev_len < 15:
            return False
        ratio = prev_len / orig_len
        # LEKTOR: stroga provjera (prijevod→HR ne smije puno rasti/padati)
        if uloga == "LEKTOR" and (ratio < 0.92 or ratio > 1.12):
            return True
        # PREVODILAC: HR je obično 10-30% duži od EN — šire granice
        if uloga == "PREVODILAC" and (ratio < 0.70 or ratio > 1.50):
            return True
    except Exception:
        pass
    return False


def detektuj_tip_bloka(html_chunk: str) -> str:
    """
    Određuje tip bloka na osnovu HTML sadržaja.
    Vraća: 'dijalog' | 'poetski' | 'opis' | 'naracija'
    """
    cist = BeautifulSoup(html_chunk, "html.parser").get_text()

    dialog_markers = len(re.findall(r'(?:^|\n)\s*[—"„]', cist))
    recjenice = [r.strip() for r in re.split(r"[.!?]+", cist) if r.strip()]
    if recjenice:
        dash_count = len(re.findall(r"[—–-]{1,2}", cist))
        quote_count = len(re.findall(r'[„""\']+ ', cist))
        if (dialog_markers / max(1, len(recjenice)) > 0.25
                or (dash_count + quote_count) > len(recjenice) * 0.4):
            return "dijalog"

    br_count = len(re.findall(r"<br\s*/?>", html_chunk, re.IGNORECASE))
    em_block = bool(re.search(
        r"<(?:em|i)[^>]*>.*?</(?:em|i)>", html_chunk, re.IGNORECASE | re.DOTALL
    ))
    prosjecna_duljina = (
        sum(len(r) for r in recjenice) / max(1, len(recjenice)) if recjenice else 0
    )
    if br_count >= 3 or (em_block and prosjecna_duljina < 60):
        return "poetski"
    if prosjecna_duljina < 40 and len(recjenice) >= 3:
        return "poetski"

    glagoli_govora = len(re.findall(
        r"\b(?:said|told|asked|replied|whispered|shouted|answered"
        r"|reče|odvrati|upita|prošaputa)\b",
        cist, re.IGNORECASE,
    ))
    if prosjecna_duljina > 120 and glagoli_govora == 0:
        return "opis"

    return "naracija"


def _adaptive_temp(uloga: str, tip_bloka: str, bazna_temp: float) -> float:
    if uloga in ("LEKTOR", "GUARDIAN"):
        if tip_bloka == "dijalog":
            return min(bazna_temp + 0.15, 0.72)
        if tip_bloka == "poetski":
            return min(bazna_temp + 0.25, 0.82)
        if tip_bloka == "opis":
            return min(bazna_temp + 0.05, 0.55)
    if uloga == "POLISH":
        if tip_bloka == "poetski":
            return 0.85
        if tip_bloka == "dijalog":
            return 0.75
        if tip_bloka == "opis":
            return 0.60
    if uloga == "PREVODILAC":
        if tip_bloka == "dijalog":
            return min(bazna_temp + 0.08, 0.30)
        if tip_bloka == "poetski":
            return min(bazna_temp + 0.15, 0.38)
    return bazna_temp


def _post_process_tipografija(tekst: str) -> str:
    """
    Post-processing tipografskih konvencija za BS/HR standard.
    """
    # Tri tačke
    tekst = re.sub(r"(?<!\.)\.\.\.(?!\.)", "…", tekst)
    tekst = re.sub(r"(?<![.\…])\.\.(?![.\…])", ".", tekst)

    # Dijalog em-crtica
    tekst = re.sub(r"(?m)^\s*--\s*", "— ", tekst)
    tekst = re.sub(r"(?m)^\s*-\s+(?=[A-ZČĆŠŽĐ])", "— ", tekst)

    # En-crtica za raspone brojeva
    tekst = re.sub(r"(\d)\s*-\s*(\d)", r"\1–\2", tekst)

    # Em-crtica bez razmaka → s razmacima
    tekst = re.sub(r"(?<=[^\s\n])—(?=[^\s\n])", " — ", tekst)

    # Whitespace ispred interpunkcije
    tekst = re.sub(r"\s+([,;:!?])", r"\1", tekst)

    return tekst


def _automatska_korekcija(tekst: str) -> str:
    """
    B07 FIX: Sada strip HTML tagova prije regex matchinga, pa vrati HTML strukturu.
    Prošireno s više kalkova koji su bili propušteni.
    """
    # Radi na čistom tekstu → primijeni korekcije → tekst se vraća u HTML blok
    # NAPOMENA: korekcije se primjenjuju samo na text nodove, HTML tagovi ostaju
    def _korigiraj_cist(cist: str) -> str:
        zamjene = [
            (r"\bbio\s+je\s+u\s+stanju\s+da\b",         "mogao je"),
            (r"\bbila\s+je\s+u\s+stanju\s+da\b",         "mogla je"),
            (r"\bnije\s+bio\s+u\s+mogu[ćc]nosti\b",      "nije mogao"),
            (r"\bnije\s+bila\s+u\s+mogu[ćc]nosti\b",     "nije mogla"),
            (r"\buspio\s+je\s+da\s+uradi\b",              "uspio je uraditi"),
            (r"\bpokušao\s+je\s+da\b",                    "pokušao je"),
            (r"\bpokušala\s+je\s+da\b",                   "pokušala je"),
            (r"\bu\s+pogledu\s+toga\b",                   "što se toga tiče"),
            (r"\bimati\s+u\s+vidu\b",                     "imati na umu"),
            (r"\bna\s+kraju\s+krajeva\b",                 "naposljetku"),
        ]
        for pattern, zamjena in zamjene:
            cist = re.sub(pattern, zamjena, cist, flags=re.IGNORECASE)
        return cist

    # Parsiramo HTML, korigiramo samo tekst nodove
    try:
        soup = BeautifulSoup(tekst, "html.parser")
        for node in soup.find_all(string=True):
            korigiran = _korigiraj_cist(node.string)
            if korigiran != node.string:
                node.replace_with(korigiran)
        return str(soup)
    except Exception:
        # Fallback: direktna zamjena na cijelom tekstu
        return _korigiraj_cist(tekst)