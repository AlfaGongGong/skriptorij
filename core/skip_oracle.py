"""
Skip Oracle — odlučuje da li AI korak može biti preskočen.
BEZ DEGRADACIJE: preskače samo kad je sigurnost >= 95%.
Koristi SAMO determinističke metrike (bez AI-ja).
"""

import re
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

# Pragovi — BEZ DEGRADACIJE (konzervativni)
MIN_SCORE_ZA_SKIP = 8.5        # samo odlični blokovi mogu skipovati
MAX_LEKTOR_PROMJENA = 0.05     # lektor smije promijeniti max 5% teksta
MIN_SLICNOST_LEKTOR_IZLAZ = 0.92  # lektor izlaz mora biti 92% sličan ulazu

def _plain_text(html_text):
    try:
        return BeautifulSoup(html_text or "", "html.parser").get_text(" ", strip=True)
    except Exception:  # NOTE #1 fix: bare except zamjenjen
        return (html_text or "").strip()

def _similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:500], b[:500]).ratio()

def _broj_rijecnih_promjena(prije, poslije):
    """Broji koliko je riječi promijenjeno (precizna metrika)."""
    rijeci_prije = set(re.findall(r'\b\w+\b', prije.lower()))
    rijeci_poslije = set(re.findall(r'\b\w+\b', poslije.lower()))
    if not rijeci_prije:
        return 0
    promijenjene = rijeci_prije.symmetric_difference(rijeci_poslije)
    return len(promijenjene) / len(rijeci_prije)

def moze_skipovati_korektor(prevod_score, lektor_ulaz, lektor_izlaz):
    """
    Odlučuje da li KOREKTOR može biti preskočen.
    
    BEZ DEGRADACIJE: svi uslovi moraju biti zadovoljeni:
    1. Prevod score >= 8.5
    2. Lektor nije značajno promijenio tekst (< 5% riječi)
    3. Lektor izlaz je jako sličan ulazu (>= 92%)
    """
    if prevod_score < MIN_SCORE_ZA_SKIP:
        return False, f"score {prevod_score:.1f} < {MIN_SCORE_ZA_SKIP}"
    
    if not lektor_ulaz or not lektor_izlaz:
        return False, "prazan tekst"
    
    plain_ulaz = _plain_text(lektor_ulaz)
    plain_izlaz = _plain_text(lektor_izlaz)
    
    # Metrika 1: Procenat promijenjenih riječi
    promjena = _broj_rijecnih_promjena(plain_ulaz, plain_izlaz)
    if promjena > MAX_LEKTOR_PROMJENA:
        return False, f"lektor promijenio {promjena:.1%} riječi > {MAX_LEKTOR_PROMJENA:.0%}"
    
    # Metrika 2: Sličnost izlaza sa ulazom
    slicnost = _similarity(plain_ulaz, plain_izlaz)
    if slicnost < MIN_SLICNOST_LEKTOR_IZLAZ:
        return False, f"sličnost {slicnost:.2f} < {MIN_SLICNOST_LEKTOR_IZLAZ}"
    
    return True, f"preskok (score={prevod_score:.1f}, promjena={promjena:.1%}, sličnost={slicnost:.2f})"

def moze_skipovati_lektora(tekst_je_vec_bs_hr, en_ratio):
    """
    Odlučuje da li LEKTOR može biti preskočen za tekst koji je već na BS/HR.
    BEZ DEGRADACIJE: samo ako je EN ratio < 3% i tekst dovoljno dug.
    """
    plain = _plain_text(tekst_je_vec_bs_hr)
    if len(plain) < 100:
        return False, "prekratak tekst"
    if en_ratio > 0.03:
        return False, f"EN ratio {en_ratio:.1%} > 3%"
    return True, "tekst već na BS/HR, EN<3%"
