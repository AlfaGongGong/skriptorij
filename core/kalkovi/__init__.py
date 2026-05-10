"""
core/kalkovi/__init__.py
"""
from .kalkovi_da import KALKOVI as _DA
from .ekavizmi import EKAVIZMI as _EKAVIZMI
from core.kalkovi.pleonazmi import PLEONAZMI
from core.kalkovi.dijalog import DIJALOG
from core.kalkovi.glagoli import GLAGOLI

# Dinamički promovirani kalkovi (iz karantene)
try:
    from core.kalkovi.dinamicki_lista import DINAMICKI_KALKOVI as _DINAMICKI
except Exception:
    _DINAMICKI = []

SVE_LISTE = _DA + _EKAVIZMI + _DINAMICKI

__all__ = ["SVE_LISTE", "_DA", "_EKAVIZMI", "_DINAMICKI", "reload_dinamicki_kalkove"]


def reload_dinamicki_kalkove() -> int:
    """
    Reučitava dinamički generirane kalkove iz dinamicki_lista.py
    i ažurira globalni kalkovi_engine novim listama.
    Vraća ukupan broj aktivnih patterna.
    """
    import sys
    global _DINAMICKI, SVE_LISTE

    mod_name = "core.kalkovi.dinamicki_lista"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    try:
        from core.kalkovi.dinamicki_lista import DINAMICKI_KALKOVI as _new_din
        _DINAMICKI = _new_din
    except Exception:
        _DINAMICKI = []

    SVE_LISTE = _DA + _EKAVIZMI + _DINAMICKI

    try:
        from core.kalkovi.engine import kalkovi_engine
        kalkovi_engine.reload(SVE_LISTE)
    except Exception:
        pass

    return len(SVE_LISTE)

# ── Morfologija blacklist (Korak 3) ────────────────────────────────────────
try:
    from core.kalkovi.morfologija_blacklist import (
        BLACKLIST_PROMPT_BLOK,
        HALUCIRANI_OBLICI,
        HALUCINACIJA_WHITELIST,
        skeniraj_halucinacije,
    )
    _MORFOLOGIJA_BLACKLIST_DOSTUPNA = True
except ImportError:
    BLACKLIST_PROMPT_BLOK = ""
    HALUCIRANI_OBLICI = {}
    HALUCINACIJA_WHITELIST = set()
    def skeniraj_halucinacije(tekst): return []
    _MORFOLOGIJA_BLACKLIST_DOSTUPNA = False
