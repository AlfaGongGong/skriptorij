# core/text_utils.py
import re
import json
from bs4 import BeautifulSoup

_HR_DIACRITICALS = frozenset("šćčžđŠĆČŽĐ")

def _smart_extract(raw: str) -> str:
    if not raw: return ""
    raw = raw.strip()
    if raw.startswith("```"): raw = re.sub(r"^```(?:json)?\s*", "", raw); raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for k in ["finalno_polirano","korektura","tekst"]:
                if k in data and data[k]: return str(data[k]).strip()
    except: pass
    m = re.search(r'"finalno_polirano"\s*:\s*"([^"]+)"', raw)
    if m: return m.group(1)
    return _agresivno_cisti(raw)

def _agresivno_cisti(tekst: str) -> str:
    if not tekst: return ""
    tekst = re.sub(r"```.*?```", "", tekst, flags=re.DOTALL)
    tekst = re.sub(r"<OVDJE_IDI_[A-Z_]+>", "", tekst)
    return _ocisti_ai_markere(tekst.strip())

def _ocisti_ai_markere(tekst: str) -> str:
    for p in [r"\bNaravno[,!]?\b", r"\bSvakako[,!]?\b", r"Evo (?:rezultata|prijevoda)", r"Izvolite"]:
        tekst = re.sub(p, "", tekst, flags=re.IGNORECASE)
    return tekst.strip()

def _je_placeholder(tekst: str) -> bool:
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    return cist in {"lektorisani tekst ovdje", "korigirani tekst ovdje"}

_EN_STOPWORDS = frozenset({"the","and","was","for","with","his","they","have","from","this","that"})
def _detektuj_en_ostatke(tekst: str) -> float:
    try:
        cist = re.sub(r"<[^>]+>", "", tekst).lower()
        if any(c in _HR_DIACRITICALS for c in cist): return 0.0
        words = re.findall(r"\b[a-z]{2,}\b", cist)
        if not words: return 0.0
        return sum(1 for w in words if w in _EN_STOPWORDS) / len(words)
    except: return 0.0

def _detektuj_halucinaciju(original: str, prijevod: str, uloga: str = "LEKTOR") -> bool:
    try:
        orig_len = len(re.sub(r"<[^>]+>", "", original).strip())
        prev_len = len(re.sub(r"<[^>]+>", "", prijevod).strip())
        if orig_len == 0 or prev_len < 15: return False
        ratio = prev_len / orig_len
        if uloga == "LEKTOR" and (ratio < 0.92 or ratio > 1.12): return True
    except: pass
    return False

def _adaptive_temp(uloga: str, tip_bloka: str, bazna_temp: float) -> float:
    if uloga in ("LEKTOR","GUARDIAN"):
        if tip_bloka == "dijalog": return min(bazna_temp+0.15, 0.72)
        if tip_bloka == "poetski": return min(bazna_temp+0.25, 0.82)
    if uloga == "POLISH":
        if tip_bloka == "poetski": return 0.85
        if tip_bloka == "dijalog": return 0.75
    return bazna_temp

def _post_process_tipografija(tekst: str) -> str:
    tekst = re.sub(r"\.\.\.", "…", tekst)
    tekst = re.sub(r"\s+([,;:!?])", r"\1", tekst)
    return tekst

def _automatska_korekcija(tekst: str) -> str:
    tekst = re.sub(r"\bbio\s+je\s+u\s+stanju\s+da\b", "mogao je", tekst, flags=re.IGNORECASE)
    return tekst
