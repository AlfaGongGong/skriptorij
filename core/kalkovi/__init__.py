"""
core/kalkovi/__init__.py
"""
from .kalkovi_da import KALKOVI as _DA
from .ekavizmi import EKAVIZMI as _EKAVIZMI
from core.kalkovi.pleonazmi import PLEONAZMI
from core.kalkovi.dijalog import DIJALOG
from core.kalkovi.glagoli import GLAGOLI

SVE_LISTE = _DA + _EKAVIZMI

__all__ = ["SVE_LISTE", "_DA", "_EKAVIZMI"]

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
