# rate_limiter.py
# ISPRAVKE:
#   BUG#1 FIX: Uklonjen duplikat bloka (import asyncio as _asyncio_rl + cijeli semafor blok)
#   BUG#4 FIX: _ensure_provider_lock ne kreira Lock unutar threading lock-a —
#               asyncio.Lock() se kreira isključivo unutar async konteksta
#   BUG#8 FIX: _get_provider_lock uklonjena (bila mrtva i pogrešna)
#   BUG#THROTTLE FIX (v10.5): _LAST_CALLS je bio per-provider globalna varijabla —
#     serijalizirala je SVE ključeve istog provajdera. Svaki ključ je čekao puni
#     min_gap (5s za Gemini) od zadnjeg poziva BILO KOJEG ključa istog provajdera.
#     S 6 Gemini ključeva: throughput = 1 req/5s umjesto 6 req/5s.
#     Ispravljeno: _LAST_CALLS_KEY per-key dict (key_string → timestamp).
#     _LAST_CALLS (per-provider) ostaje samo za startup anti-burst jitter.

import asyncio
import random
import time

# ===== GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita =====
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}          # per-provider: koristi se samo za startup anti-burst jitter
_LAST_CALLS_KEY: dict = {}  # BUG#THROTTLE FIX: per-key timestamp (key_string → float)
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
# BUG#12 FIX (KRITIČNO): asyncio.Semaphore ne pruža zaštitu između THREADOVA.
#   App pokreće više pozadinskih threadova koji svaki pozivaju asyncio.run(),
#   što znači N paralelnih event loop-ova. Svaki thread kreirao je VLASTITI
#   asyncio.Semaphore za isti ključ → zaštita "max 1 paralelni poziv po ključu"
#   bila je POTPUNO NEFUNKCIONALNA između threadova.
#   Posljedica: više threadova moglo je istovremeno poslati zahtjev s istim
#   ključem, što uzrokuje 429 čak i na svježim (nekorišćenim) ključevima.
#   Ispravak: threading.Semaphore koji je process-wide (ne vezan za event loop).
#   Akvizicija u async kontekstu ide kroz asyncio.to_thread da ne blokira loop.
# ============================================================================

import threading as _threading

# _key_semaphores: key -> threading.Semaphore  (process-wide, cross-thread)
_key_semaphores: dict[str, _threading.Semaphore] = {}
_key_semaphores_lock = _threading.Lock()
MAX_CONCURRENT_PER_KEY = 1


def get_key_semaphore(key: str) -> _threading.Semaphore:
    """Vraća process-wide threading.Semaphore za dati ključ (lazy init)."""
    with _key_semaphores_lock:
        if key not in _key_semaphores:
            _key_semaphores[key] = _threading.Semaphore(MAX_CONCURRENT_PER_KEY)
        return _key_semaphores[key]

async def _throttle_provider(provider: str | None, key: str | None = None) -> None:
    """
    Throttle po ključu + provider-level cooldown provjera.

    BUG_C FIX: Prethodna verzija je koristila provider-level asyncio.Lock koji je
    serijalizirao SVE pozive prema provideru. S više ključeva to znači da ključevi
    čekaju jedan na drugog umjesto da rade paralelno — direktno suprotno svrsi flota.

    BUG#THROTTLE FIX: _LAST_CALLS je bio per-provider — serijalizirao je sve ključeve
    istog provajdera. Svaki ključ čekao puni min_gap od zadnjeg poziva BILO KOJEG
    ključa. S 6 Gemini ključeva to znači 1 req/5s umjesto 6 req/5s (throughput
    faktorno manji od kapaciteta). Ispravljeno: throttle je sada per-key putem
    _LAST_CALLS_KEY. Provider-level _LAST_CALLS ostaje samo za startup anti-burst.
    """
    if not provider:
        return

    prov = provider.upper()

    # Provjeri provider cooldown (kratko, bez locka — samo čitanje)
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

    # BUG#THROTTLE FIX: koristi per-key timestamp, ne per-provider.
    # Svaki ključ ima vlastitu liniju vremena — ključevi rade paralelno,
    # svaki poštuje vlastiti min_gap od svog zadnjeg poziva.
    gap = base_gap + random.uniform(_JITTER_MIN, _JITTER_MAX)
    if key:
        last = _LAST_CALLS_KEY.get(key, 0.0)
    else:
        # Fallback za pozive bez ključa — per-provider (staro ponašanje)
        last = _LAST_CALLS.get(prov, 0.0)

    wait = (last + gap) - now
    if wait > 0:
        await asyncio.sleep(wait)

    # Ažuriraj per-key timestamp
    now2 = time.time()
    if key:
        _LAST_CALLS_KEY[key] = now2
    else:
        _LAST_CALLS[prov] = now2


async def acquire_key(key: str, provider: str | None = None):
    sem = get_key_semaphore(key)
    # BUG#12 FIX: koristimo threading.Semaphore (process-wide) umjesto asyncio.Semaphore.
    # asyncio.to_thread akvizira semafor u thread pool-u bez blokiranja event loop-a.
    # Ovo garantuje da samo jedan thread istovremeno koristi isti ključ.
    await asyncio.to_thread(sem.acquire)
    # BUG#THROTTLE FIX: prosljeđujemo key da _throttle_provider koristi per-key timing
    await _throttle_provider(provider, key=key)

def release_key(key: str):
    sem = _key_semaphores.get(key)
    if sem is not None:
        sem.release()
