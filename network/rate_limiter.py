# rate_limiter.py
# ISPRAVKE:
#   BUG#1 FIX: Uklonjen duplikat bloka (import asyncio as _asyncio_rl + cijeli semafor blok)
#   BUG#4 FIX: _ensure_provider_lock ne kreira Lock unutar threading lock-a —
#               asyncio.Lock() se kreira isključivo unutar async konteksta
#   BUG#8 FIX: _get_provider_lock uklonjena (bila mrtva i pogrešna)

import asyncio
import random
import time

# ===== GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita =====
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}
_PROVIDER_COOLDOWN_UNTIL: dict = {}
_PROVIDER_DYNAMIC_GAP: dict = {}

# ── Per-provider minimalni gap — iz provider_profiles.py ─────────────────────
# Razmak između poziva JEDNOG ključa = 60s / rpm_safe
# Ne treba se mijenjati ovdje — mijenja se u provider_profiles.py
try:
    from network.provider_profiles import get_min_gap as _get_provider_min_gap
    def _provider_gap(prov: str) -> float:
        return _get_provider_min_gap(prov)
except ImportError:
    # Fallback iz profila ako import nije dostupan
    _PROVIDER_MIN_GAP_FALLBACK = {
        "GEMINI": 5.0,   "GROQ": 2.5,   "CEREBRAS": 2.5,  "SAMBANOVA": 7.5,
        "MISTRAL": 62.0, "COHERE": 3.75, "OPENROUTER": 4.0, "GITHUB": 7.5,
        "TOGETHER": 3.75, "FIREWORKS": 3.75, "CHUTES": 7.5,
        "HUGGINGFACE": 8.6, "KLUSTER": 5.0, "GEMMA": 7.5,
    }
    def _provider_gap(prov: str) -> float:
        return _PROVIDER_MIN_GAP_FALLBACK.get(prov.upper(), 5.0)

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
        if default is not None:
            return default
        # BUG-C FIX: gemma-3-27b-it je 404 od maja 2026 — koristimo gemini-2.0-flash
        return "gemini-2.0-flash" if prov_upper == "GEMINI" else None

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


def register_provider_backoff(provider: str | None, retry_after: float | None) -> None:
    """
    Registruje provider-level backoff (sekunde) nakon 429.
    Sljedeći zahtjevi prema tom provideru čekaju bar do ovog roka.
    """
    if not provider:
        return
    try:
        ra = float(retry_after) if retry_after is not None else 0.0
    except (TypeError, ValueError):
        return
    if ra <= 0:
        return

    prov = provider.upper()
    until = time.time() + ra
    prev = _PROVIDER_COOLDOWN_UNTIL.get(prov, 0.0)
    if until > prev:
        _PROVIDER_COOLDOWN_UNTIL[prov] = until


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _header_float(headers, names):
    if not headers:
        return None
    for name in names:
        v = headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
        fv = _to_float(v)
        if fv is not None:
            return fv
    return None


def _extract_total_tokens(body) -> float | None:
    if not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if total is None:
        prompt = _to_float(usage.get("prompt_tokens")) or 0.0
        completion = _to_float(usage.get("completion_tokens")) or 0.0
        total = prompt + completion
    return _to_float(total)


def register_provider_runtime_limits(provider: str | None, headers=None, body=None) -> None:
    """
    Ažurira dinamički provider gap iz stvarno opaženih limita/usage-a.
    Koristi RPM/TPM limite iz headera + usage.total_tokens iz body-a (ako postoji).
    """
    if not provider:
        return
    prov = provider.upper()

    rpm_limit = _header_float(headers, [
        "x-ratelimit-limit-requests",
        "ratelimit-limit",
        "x-limit-requests",
    ])
    tpm_limit = _header_float(headers, [
        "x-ratelimit-limit-tokens",
        "ratelimit-limit-tokens",
        "x-limit-tokens",
    ])
    token_cost = _extract_total_tokens(body)

    rpm_gap = (60.0 / rpm_limit) if (rpm_limit and rpm_limit > 0) else 0.0
    tpm_gap = (60.0 * token_cost / tpm_limit) if (tpm_limit and tpm_limit > 0 and token_cost and token_cost > 0) else 0.0

    observed_gap = max(rpm_gap, tpm_gap, 0.0)
    if observed_gap <= 0:
        return

    # Blagi safety faktor; ograniči da ne ode u ekstrem zbog outliera.
    observed_gap = min(observed_gap * 1.15, 20.0)

    prev = _PROVIDER_DYNAMIC_GAP.get(prov, 0.0)
    if prev <= 0:
        _PROVIDER_DYNAMIC_GAP[prov] = observed_gap
    else:
        # EWMA: reaguje i na rast i na pad, bez naglih skokova.
        _PROVIDER_DYNAMIC_GAP[prov] = (0.70 * prev) + (0.30 * observed_gap)

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

async def _throttle_provider(provider: str | None) -> None:
    """
    Globalni throttle po provideru (nezavisno od broja ključeva).

    BUG_C FIX: Prethodna verzija je koristila provider-level asyncio.Lock koji je
    serijalizirao SVE pozive prema provideru. S više ključeva to znači da ključevi
    čekaju jedan na drugog umjesto da rade paralelno — direktno suprotno svrsi flota.

    Nova verzija: provider lock se koristi samo za provjeru cooldown-a (kratko).
    Sam throttle (sleep) se izvodi VAN lock-a da se ne blokiraju drugi ključevi.
    Gemini multiplikator je uklonjen — per-key semaphore (MAX_CONCURRENT_PER_KEY=1)
    već osigurava da isti ključ nema paralelnih poziva.
    """
    if not provider:
        return

    prov = provider.upper()

    # Provjeri provider cooldown (kratko, uz lock)
    provider_cooldown_until = _PROVIDER_COOLDOWN_UNTIL.get(prov, 0.0)
    now = time.time()
    if provider_cooldown_until > now:
        wait = provider_cooldown_until - now
        # Ograniči čekanje: ne blokiraj duže od 30s u throttle funkciji —
        # per-key cooldown u KeyState je zadužen za dulja blokiranja.
        if wait > 30.0:
            wait = 0.0
        if wait > 0:
            await asyncio.sleep(wait)
            now = time.time()

    base_gap = _provider_gap(prov)
    dynamic_gap = _PROVIDER_DYNAMIC_GAP.get(prov, 0.0)
    if dynamic_gap > 0:
        base_gap = max(base_gap, dynamic_gap)

    # BUG_C FIX: Uklonjeno Gemini/Gemma množenje s _RPM_THROTTLE_MULTIPLIER (1.8).
    # Per-key semaphore (MAX_CONCURRENT_PER_KEY=1) osigurava serializaciju po ključu.
    # Provider-level množenje je blokiralo paralelne pozive s RAZLIČITIM ključevima.

    gap = base_gap + random.uniform(_JITTER_MIN, _JITTER_MAX)
    last = _LAST_CALLS.get(prov, 0.0)
    wait = (last + gap) - now
    if wait > 0:
        await asyncio.sleep(wait)

    _LAST_CALLS[prov] = time.time()


async def acquire_key(key: str, provider: str | None = None):
    sem = get_key_semaphore(key)
    await sem.acquire()
    await _throttle_provider(provider)

def release_key(key: str):
    entry = _key_semaphores.get(key)
    if entry is not None:
        _, sem = entry
        sem.release()
