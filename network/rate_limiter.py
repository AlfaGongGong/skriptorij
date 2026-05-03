# rate_limiter.py
# ISPRAVKE:
#   BUG#1 FIX: Uklonjen duplikat bloka (import asyncio as _asyncio_rl + cijeli semafor blok)
#   BUG#4 FIX: _ensure_provider_lock ne kreira Lock unutar threading lock-a —
#               asyncio.Lock() se kreira isključivo unutar async konteksta
#   BUG#8 FIX: _get_provider_lock uklonjena (bila mrtva i pogrešna)

import time
import asyncio
import threading as _thr_rl
from api_fleet import FleetManager

# ===== GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita =====
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}

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


# BUG#4 FIX: asyncio.Lock() se SMIJE kreirati samo unutar aktivnog event loop-a.
# Rješenje: ne koristimo threading Lock za dvostruku provjeru —
# umjesto toga koristimo asyncio-safe lazy init unutar async funkcije.
async def _ensure_provider_lock(prov: str) -> asyncio.Lock:
    """Vrati per-provider asyncio.Lock — lazy init unutar async konteksta."""
    # Provjeri bez blokiranja (read je thread-safe za dict u CPythonu)
    lock = _PROVIDER_LOCKS.get(prov)
    if lock is None:
        # Kreiraj novi Lock unutar trenutnog event loop-a
        lock = asyncio.Lock()
        # Samo ako još uvijek nije postavljen (race condition između coroutina)
        _PROVIDER_LOCKS.setdefault(prov, lock)
        # Vrati ono što je u dictu (može biti drugačiji Lock ako je race)
        lock = _PROVIDER_LOCKS[prov]
    return lock


async def _ensure_global_lock() -> asyncio.Lock:
    """Lazy initialization of global asyncio Lock in the current event loop."""
    return await _ensure_provider_lock("__global__")


def _safe_get_model(fleet, prov_upper, default=None):
    """Sigurno dohvati aktivan model — ne crasha ako FleetManager nema tu metodu."""
    try:
        return fleet.get_active_model(prov_upper)
    except (AttributeError, KeyError):
        return (
            default
            if default is not None
            else ("gemma-3-27b-it" if prov_upper == "GEMINI" else None)
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
            for k, v in (raw.items() if isinstance(raw, dict) else {}):
                setattr(fks, k, v)
            return fks
    except Exception:
        pass
    return None


# ============================================================================
# Per-key rate limiting (semafori)
# BUG#1 FIX: Ovaj blok je bio dupliran — uklonjen drugi primjerak.
# ============================================================================

_key_semaphores: dict = {}
MAX_CONCURRENT_PER_KEY = 1


def get_key_semaphore(key: str) -> asyncio.Semaphore:
    if key not in _key_semaphores:
        _key_semaphores[key] = asyncio.Semaphore(MAX_CONCURRENT_PER_KEY)
    return _key_semaphores[key]


async def acquire_key(key: str):
    sem = get_key_semaphore(key)
    await sem.acquire()


def release_key(key: str):
    sem = _key_semaphores.get(key)
    if sem:
        sem.release()