# rate_limiter.py
# Automatski generisano iz skriptorij.py

import re
import json
import time
import random
import asyncio
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
from api_fleet import FleetManager

# ===== GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita =====
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}


def _get_provider_lock(prov: str):
    """Vrati asyncio.Lock specifičan za ovaj provajder (lazy init)."""
    if prov not in _PROVIDER_LOCKS:
        _PROVIDER_LOCKS[prov] = None
    return prov


_PROVIDER_MIN_GAP = {
    "GEMINI": 4.0,
    "GROQ": 2.5,
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
    """Vrati per-provider asyncio.Lock (lazy init, thread-safe)."""
    if _PROVIDER_LOCKS.get(prov) is None:
        _PROVIDER_LOCKS[prov] = asyncio.Lock()
    return _PROVIDER_LOCKS[prov]


async def _ensure_global_lock():
    return await _ensure_provider_lock("__global__")


def _safe_get_model(fleet, prov_upper, default=None):
    """Sigurno dohvati aktivan model — ne crasha ako FleetManager nema tu metodu."""
    try:
        return fleet.get_active_model(prov_upper)
    except (AttributeError, KeyError):
        return (
            default
            if default is not None
            else ("gemini-2.5-flash" if prov_upper == "GEMINI" else None)
        )


def _get_key_state(fleet, prov_upper: str, key: str):
    """Sigurno dohvati KeyState objekt za dati ključ."""
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

