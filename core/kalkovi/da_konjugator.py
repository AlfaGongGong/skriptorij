# core/kalkovi/da_konjugator.py
"""
Konjugator "modal + da + glagol" → "modal + infinitiv".

Pravilo: pretvaraj SAMO kad su modal i glagol u ISTOM licu.
To garantuje da je subjekt isti, pa je infinitiv gramatički ispravan.

Primjeri:
  ✅ "želim da radim"     → "želim raditi"     (1sg + 1sg)
  ✅ "želimo da radimo"   → "želimo raditi"    (1pl + 1pl)
  ✅ "želiš da radiš"     → "želiš raditi"     (2sg + 2sg)
  ✅ "želi da radi"       → "želi raditi"      (3sg + 3sg)
  ❌ "želiš da radim"     → ostavi            (2sg ≠ 1sg)
  ❌ "želimo da idu"      → ostavi            (1pl ≠ 3pl)
  ❌ "Mogu da idem kući"  → "Mogu ići kući"    (opcionalno)
"""

from __future__ import annotations
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from .glagoli_mapa import dobij_glagol, dobij_modal_lice
    _MAPA_OK = True
except ImportError:
    _MAPA_OK = False
    logger.warning("[da_konjugator] glagoli_mapa nije dostupna")


# Regex: (modal) da (glagol)
_DA_PATTERN = re.compile(
    r'\b([a-zA-ZčćžšđČĆŽŠĐ]+)\s+da\s+([a-zA-ZčćžšđČĆŽŠĐ]+)\b',
    re.UNICODE
)


def konjuguj(tekst: str, agresivno: bool = False) -> tuple[str, int]:
    """
    Pretvara "modal + da + glagol" u "modal + infinitiv" kad su ista lica.
    
    Args:
        tekst:      HTML ili plain tekst
        agresivno:  Ako True, mijenjaj i kad su različita lica (nije sigurno!)
    
    Returns:
        (novi_tekst, broj_zamjena)
    """
    if not tekst or not _MAPA_OK:
        return tekst, 0

    # Zaštita HTML tagova — ne diraj atribute
    # Jednostavan pristup: radi na segmentima između HTML tagova
    delovi = re.split(r'(<[^>]+>)', tekst)
    broj_zamjena = 0

    for i, deo in enumerate(delovi):
        if deo.startswith('<'):
            continue  # HTML tag — preskoči

        novi_deo, n = _konjuguj_segment(deo, agresivno)
        if n > 0:
            delovi[i] = novi_deo
            broj_zamjena += n

    return "".join(delovi), broj_zamjena


def _konjuguj_segment(tekst: str, agresivno: bool) -> tuple[str, int]:
    """Konjugacija na jednom segmentu (bez HTML tagova)."""
    broj = 0

    def _zamjena(match: re.Match) -> str:
        nonlocal broj
        modal = match.group(1)
        glagol = match.group(2)

        modal_lice = dobij_modal_lice(modal)
        if not modal_lice:
            return match.group(0)

        glagol_info = dobij_glagol(glagol)
        if not glagol_info:
            return match.group(0)

        infinitiv, glagol_lice = glagol_info

        # Provjeri ista lica
        if not agresivno and modal_lice != glagol_lice:
            return match.group(0)

        broj += 1
        return f"{modal} {infinitiv}"

    rezultat = _DA_PATTERN.sub(_zamjena, tekst)
    return rezultat, broj


def konjuguj_batch(html_list: list) -> int:
    """Batch konjugacija nad listom HTML stringova."""
    ukupno = 0
    for i, html in enumerate(html_list):
        novi, n = konjuguj(html)
        if n > 0:
            html_list[i] = novi
            ukupno += n
    return ukupno


if __name__ == "__main__":
    testovi = [
        "želim da radim",
        "želimo da radimo",
        "želiš da radiš",
        "želi da radi",
        "Mogu da idem kući",
        "Ne mogu da vjerujem",
        "Morao je da ode",
        "želiš da radim",      # različita lica — ne mijenjaj
        "želimo da idu",       # različita lica — ne mijenjaj
        "Želim da ti pomognem", # 1sg + 2sg — ne mijenjaj
    ]

    print("Test da_konjugator:")
    print()
    for t in testovi:
        out, n = konjuguj(t)
        status = "✏️ " if n > 0 else "  "
        print(f"{status} {t!r}")
        if n > 0:
            print(f"    → {out!r}")
        print()
