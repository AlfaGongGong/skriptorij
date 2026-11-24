"""
core/kalkovi/__init__.py
"""

import logging
logger = logging.getLogger(__name__)
from core.kalkovi.dijalog import DIJALOG
from core.kalkovi.glagoli import GLAGOLI
from core.kalkovi.pleonazmi import PLEONAZMI

from .ekavizmi import EKAVIZMI as _EKAVIZMI
from .kalkovi_da import KALKOVI as _DA

# Dinamički promovirani kalkovi (iz karantene)
try:
    from core.kalkovi.dinamicki_lista import DINAMICKI_KALKOVI as _DINAMICKI
except Exception:
    _DINAMICKI = []


# FIX 2026-09-25: filtriraj SVE_LISTE — ukloni entry-e koji nisu tuple/list 2+
def _filtriraj(lista):
    out = []
    for e in lista:
        if isinstance(e, (tuple, list)):
            if len(e) >= 2:
                out.append(tuple(e))
            elif len(e) == 1:
                out.append((e[0], ""))
        elif isinstance(e, str):
            # String je pattern bez zamjene (rijetko korisno) — preskoči
            continue
    return out


def _dinamicki_oznaci(lista):
    """Dinamički kalkovi idu s oznakom 'dinamicki': engine ih primjenjuje samo kao cijele riječi."""
    return [(e[0], e[1], "dinamicki") for e in _filtriraj(lista)]


def _sastavi_liste(dinamicki):
    return (
        _filtriraj(_DA)
        + _filtriraj(_EKAVIZMI)
        + _dinamicki_oznaci(dinamicki)
        + _filtriraj(DIJALOG)
        + _filtriraj(PLEONAZMI)
        + _filtriraj(GLAGOLI)
    )


# Kategorija = naziv modula (za statistiku i dnevnik zamjena; R11a-18)
_KATEGORIJE = ("da", "ekavizmi", "dinamicki", "dijalog", "pleonazmi", "glagoli")


def _sastavi_kat(dinamicki):
    """Isti unosi kao _sastavi_liste, ali treći član je naziv modula."""
    izvori = (
        ("da", _filtriraj(_DA)),
        ("ekavizmi", _filtriraj(_EKAVIZMI)),
        ("dinamicki", _filtriraj(dinamicki)),
        ("dijalog", _filtriraj(DIJALOG)),
        ("pleonazmi", _filtriraj(PLEONAZMI)),
        ("glagoli", _filtriraj(GLAGOLI)),
    )
    return [(e[0], e[1], naziv) for naziv, lista in izvori for e in lista]


SVE_LISTE = _sastavi_liste(_DINAMICKI)
SVE_LISTE_KAT = _sastavi_kat(_DINAMICKI)

__all__ = [
    "SVE_LISTE",
    "SVE_LISTE_KAT",
    "_DA",
    "_EKAVIZMI",
    "_DINAMICKI",
    "PLEONAZMI",
    "DIJALOG",
    "GLAGOLI",
    "reload_dinamicki_kalkove",
]


def reload_dinamicki_kalkove() -> int:
    """
    Reučitava dinamičke kalkove i gradi NOVU listu za engine istim filterom kao pri
    startu. Engine je zamijeni tek kad je uspješno složena (pri grešci ostaje stara).
    Vraća broj patterna koje engine stvarno ima aktivne.
    """
    import sys

    global _DINAMICKI, SVE_LISTE, SVE_LISTE_KAT

    mod_name = "core.kalkovi.dinamicki_lista"
    stari_modul = sys.modules.pop(mod_name, None)
    try:
        from core.kalkovi.dinamicki_lista import DINAMICKI_KALKOVI as _new_din

        _DINAMICKI = _new_din
    except Exception as exc:  # noqa: BLE001
        if stari_modul is not None:
            sys.modules[mod_name] = stari_modul
        logger.warning("[kalkovi] reload dinamičke liste pao (%s) — ostaje stara", exc)

    nova = _sastavi_liste(_DINAMICKI)
    nova_kat = _sastavi_kat(_DINAMICKI)
    from core.kalkovi.engine import kalkovi_engine

    kalkovi_engine.reload(nova_kat)
    SVE_LISTE = nova
    SVE_LISTE_KAT = nova_kat
    return kalkovi_engine.broj_patterna


# ── Morfologija blacklist (Korak 3) ────────────────────────────────────────
try:
    from core.kalkovi.morfologija_blacklist import (
        BLACKLIST_PROMPT_BLOK,
        HALUCINACIJA_WHITELIST,
        HALUCIRANI_OBLICI,
        skeniraj_halucinacije,
    )

    _MORFOLOGIJA_BLACKLIST_DOSTUPNA = True
except ImportError:
    BLACKLIST_PROMPT_BLOK = ""
    HALUCIRANI_OBLICI = {}
    HALUCINACIJA_WHITELIST = set()

    def skeniraj_halucinacije(tekst):
        return []

    _MORFOLOGIJA_BLACKLIST_DOSTUPNA = False