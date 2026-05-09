# rate_limiter.py
# ISPRAVKE:
#   BUG#1 FIX: Uklonjen duplikat bloka (import asyncio as _asyncio_rl + cijeli semafor blok)
#   BUG#4 FIX: _ensure_provider_lock ne kreira Lock unutar threading lock-a —
#               asyncio.Lock() se kreira isključivo unutar async konteksta
#   BUG#8 FIX: _get_provider_lock uklonjena (bila mrtva i pogrešna)

import asyncio

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
# BUG#11 FIX: _PROVIDER_LOCKS: prov -> (loop_id, asyncio.Lock) —
#   isti problem kao kod semafora: Lock vezan za stari event loop je neupotrebljiv.
async def _ensure_provider_lock(prov: str) -> asyncio.Lock:
    """Vrati per-provider asyncio.Lock — lazy init unutar async konteksta."""
    current_loop_id = id(asyncio.get_running_loop())

    entry = _PROVIDER_LOCKS.get(prov)
    if entry is not None:
        stored_loop_id, lock = entry
        if current_loop_id == stored_loop_id:
            return lock
        # Lock vezan za stari event loop — kreiramo novi

    lock = asyncio.Lock()
    _PROVIDER_LOCKS[prov] = (current_loop_id, lock)
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
# BUG#11 FIX: asyncio.Semaphore je vezan za event loop u kom je kreiran.
#   Svaki asyncio.run() poziv kreira novi event loop — stari semafori postaju
#   neupotrebljivi i bacaju "is bound to a different event loop".
#   Rješenje: čuvamo (loop_id, semaphore) par i kreiramo novi semafor ako se
#   loop_id promijenio (tj. novi asyncio.run() je pokrenut).
# ============================================================================

# _key_semaphores: key -> (loop_id, asyncio.Semaphore)
_key_semaphores: dict = {}
MAX_CONCURRENT_PER_KEY = 1

def get_key_semaphore(key: str) -> asyncio.Semaphore:
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        # Nema aktivnog event loop-a — uvijek kreiramo novi semafor jer
        # ne znamo u kom loop-u će biti prvi put korišten.
        sem = asyncio.Semaphore(MAX_CONCURRENT_PER_KEY)
        _key_semaphores[key] = (None, sem)
        return sem

    entry = _key_semaphores.get(key)
    if entry is not None:
        stored_loop_id, sem = entry
        if stored_loop_id is not None and current_loop_id == stored_loop_id:
            return sem
        # Semafor je vezan za stari event loop (ili kreiran bez loop-a) — kreiramo novi

    sem = asyncio.Semaphore(MAX_CONCURRENT_PER_KEY)
    _key_semaphores[key] = (current_loop_id, sem)
    return sem

async def acquire_key(key: str):
    sem = get_key_semaphore(key)
    await sem.acquire()

def release_key(key: str):
    entry = _key_semaphores.get(key)
    if entry is not None:
        _, sem = entry
        sem.release()