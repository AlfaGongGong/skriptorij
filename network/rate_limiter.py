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
import logging
import random
import threading
import time

from config.system_logger import syslog

logger = logging.getLogger(__name__)

# ===== GLOBALNI RATE LIMITER — humanizovano, bez kršenja limita =====
_PROVIDER_LOCKS: dict = {}
_LAST_CALLS = {}          # per-provider: koristi se samo za startup anti-burst jitter
_LAST_CALLS_KEY: dict = {}  # BUG#THROTTLE FIX: per-key timestamp (key_string → float)
_LAST_CALLS_KEY_LOCK = threading.Lock()  # štiti _LAST_CALLS_KEY od race condition-a
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
_JITTER_MIN = 1.0
_JITTER_MAX = 3.0

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


def register_provider_backoff(provider: str | None, retry_after: float | None) -> None:
    """
    Registruje provider-level backoff (sekunde) nakon 429.
    Sljedeći zahtjevi prema tom provideru čekaju bar do ovog roka.
    Propagira i u QuotaTracker (per-key cooldown).
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
        logger.warning("[rate_limiter] %s backoff registrovan: %.1fs (do %s)",
                       prov, ra, time.strftime("%H:%M:%S", time.localtime(until)))
        syslog.warning("[rate_limiter] %s backoff registrovan: %.1fs (do %s)",
                       prov, ra, time.strftime("%H:%M:%S", time.localtime(until)))

    # Propagiraj i u QuotaTracker
    try:
        from network.quota_tracker import quota_tracker
        quota_tracker.set_provider_cooldown(prov, ra, reason=f"register_provider_backoff {ra:.0f}s")
    except Exception as e:
        logger.debug("[rate_limiter] quota_tracker propagacija backoffa nije uspjela: %s", e)


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
    """
    PATCH4: Podržava više response formata za token tracking.
    
    Prioritet:
      1. Gemini native: usageMetadata.totalTokenCount
      2. OpenAI compat: usage.total_tokens (ili prompt+completion)
      3. Cohere v2:     meta.tokens.{input,output}_tokens
    """
    if not isinstance(body, dict):
        return None

    # 1. Gemini native format — usageMetadata.totalTokenCount
    usage_meta = body.get("usageMetadata")
    if isinstance(usage_meta, dict):
        total = _to_float(usage_meta.get("totalTokenCount"))
        if total and total > 0:
            return total
        # Fallback: zbroj komponenti ako totalTokenCount nije prisutan
        prompt = _to_float(usage_meta.get("promptTokenCount")) or 0.0
        candidates = _to_float(usage_meta.get("candidatesTokenCount")) or 0.0
        if prompt > 0 or candidates > 0:
            return prompt + candidates

    # 2. OpenAI compat format — usage.total_tokens
    usage = body.get("usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            prompt = _to_float(usage.get("prompt_tokens")) or 0.0
            completion = _to_float(usage.get("completion_tokens")) or 0.0
            total = prompt + completion
        result = _to_float(total)
        if result and result > 0:
            return result

    # 3. Cohere v2 format — meta.tokens
    meta = body.get("meta")
    if isinstance(meta, dict):
        tokens = meta.get("tokens")
        if isinstance(tokens, dict):
            inp = _to_float(tokens.get("input_tokens")) or 0.0
            out = _to_float(tokens.get("output_tokens")) or 0.0
            if inp > 0 or out > 0:
                return inp + out

    return None


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
        logger.info("[rate_limiter] %s: dinamički gap inicijaliziran na %.2fs", prov, observed_gap)
    else:
        # EWMA: reaguje i na rast i na pad, bez naglih skokova.
        new_gap = (0.70 * prev) + (0.30 * observed_gap)
        _PROVIDER_DYNAMIC_GAP[prov] = new_gap
        if abs(new_gap - prev) > 0.5:
            logger.debug("[rate_limiter] %s: dinamički gap ažuriran %.2fs→%.2fs (EWMA)", prov, prev, new_gap)

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

# Per-provider IP-level semaphore — ograničava ukupan broj paralelnih zahtjeva
# prema istom provideru (neovisno o broju ključeva) da se izbjegne IP ban.
_PROVIDER_SEMAPHORES: dict[str, _threading.Semaphore] = {}
_PROVIDER_SEMAPHORES_LOCK = _threading.Lock()
# FIX v13: Povećano na 2 (s 1).
# S MAX=1: 6 ključeva → throughput = 1 req / (gap+jitter) = ~1 req/8.5s
#   Svaki ključ čeka na semafor dok prethodni završi HTTP request (do 90s timeout).
#   Ako server spor → svi ključevi se "gomilaju" na semaforu → throughput pada.
# S MAX=2: 2 paralelna zahtjeva prema Googleu istovremeno, svaki s RAZLIČITIM ključem.
#   _throttle_provider (v13 fix) osigurava da svaki ključ poštuje vlastiti min_gap
#   od zadnjeg *stvarnog* slanja — burst više nije moguć jer timestamp bilježimo
#   neposredno pred slanje, a ne pri rezervaciji.
# Zašto ne 3+: Google free tier throttluje na IP nivou pri 3+ concurrent zahtjeva.
#   2 je sigurna granica — testirana empirijski (21.05 burst je bio 6 u 2.5s).
MAX_CONCURRENT_PER_PROVIDER = 2


def get_key_semaphore(key: str) -> _threading.Semaphore:
    """Vraća process-wide threading.Semaphore za dati ključ (lazy init)."""
    with _key_semaphores_lock:
        if key not in _key_semaphores:
            _key_semaphores[key] = _threading.Semaphore(MAX_CONCURRENT_PER_KEY)
        return _key_semaphores[key]


def get_provider_semaphore(provider: str) -> _threading.Semaphore:
    """Vraća process-wide threading.Semaphore za dati provajder (IP-level zaštita)."""
    prov = provider.upper()
    with _PROVIDER_SEMAPHORES_LOCK:
        if prov not in _PROVIDER_SEMAPHORES:
            _PROVIDER_SEMAPHORES[prov] = _threading.Semaphore(MAX_CONCURRENT_PER_PROVIDER)
        return _PROVIDER_SEMAPHORES[prov]


async def _throttle_provider(provider: str | None, key: str | None = None) -> None:
    """
    Throttle po ključu + provider-level cooldown provjera.

    FIX v13: Timestamp se bilježi NEPOSREDNO PRED slanje (na kraju funkcije),
    ne pri rezervaciji (na početku). Stari bug: ključ čeka na prov_sem.acquire()
    20-30s → ulazi u throttle → timestamp rezervacije je već stari → elapsed > gap
    → request ide odmah. Ako više ključeva čeka na semaforu, svi odlaze "odmah"
    kad dobiju red → burst → 429.

    Novo: svaki put kad ključ dobije red, iznova mjeri elapsed od zadnje *stvarne*
    upotrebe i čeka razliku. Timestamp = trenutak slanja. Nema lock-a → nema
    serijalizacije između ključeva istog provajdera.
    """
    if not provider:
        return

    prov = provider.upper()

    # Provjeri provider cooldown
    provider_cooldown_until = _PROVIDER_COOLDOWN_UNTIL.get(prov, 0.0)
    now = time.time()
    if provider_cooldown_until > now:
        wait = min(provider_cooldown_until - now, 120.0)
        if wait > 0:
            logger.info("[rate_limiter] %s cooldown aktivan — čekam %.1fs", prov, wait)
            await asyncio.sleep(wait)

    base_gap = _provider_gap(prov)
    dynamic_gap = _PROVIDER_DYNAMIC_GAP.get(prov, 0.0)
    if dynamic_gap > base_gap:
        logger.debug("[rate_limiter] %s: dinamički gap %.2fs > baza %.2fs", prov, dynamic_gap, base_gap)
    base_gap = max(base_gap, dynamic_gap)

    # FIX v13: čitaj STVARNI zadnji timestamp (trenutak slanja), ne timestamp rezervacije.
    # Bez lock-a na sleep-u — paralelni ključevi ne blokiraju jedni druge.
    if key:
        with _LAST_CALLS_KEY_LOCK:
            last_sent = _LAST_CALLS_KEY.get(key, 0.0)
    else:
        last_sent = _LAST_CALLS.get(prov, 0.0)

    gap = base_gap + random.uniform(0.5, 1.5)   # manji jitter (0.5-1.5s) za bolji throughput
    wait = (last_sent + gap) - time.time()

    if wait > 0:
        logger.debug("[rate_limiter] %s ...%s throttle %.2fs (gap=%.1f+jitter)",
                     prov, (key or "")[-4:], wait, base_gap)
        await asyncio.sleep(wait)

    # Bilježi SADA — neposredno pred slanje, ne pri rezervaciji
    now_sending = time.time()
    if key:
        with _LAST_CALLS_KEY_LOCK:
            _LAST_CALLS_KEY[key] = now_sending
    else:
        _LAST_CALLS[prov] = now_sending


async def acquire_key(key: str, provider: str | None = None):
    # Provjeri QuotaTracker dostupnost PRIJE nego što zauzimamo semafor
    # V2 FIX: Ako ključ nije dostupan zbog min_gap — SAČEKAJ, nemoj baciti grešku.
    # RuntimeError bi ubio chunk (ode u ERROR), a min_gap znači samo "sačekaj par sekundi".
    if provider:
        try:
            from network.quota_tracker import quota_tracker
            ok, reason = quota_tracker.is_key_available(provider, key)
            if not ok:
                # Ako je min_gap ili kratki cooldown (≤15s) — sačekaj
                # Ako je RPD iscrpljen ili dugi cooldown — baci grešku
                if "min_gap" in reason or ("cooldown" in reason and "čekanje" in reason):
                    # Izvuci broj sekundi iz reason stringa
                    import re as _re
                    match = _re.search(r'([\d.]+)s', reason)
                    wait_s = float(match.group(1)) if match else 5.0
                    wait_s = min(wait_s, 15.0)  # max 15s čekanja
                    syslog.debug(
                        "[rate_limiter] %s ...%s čekam %.1fs — %s",
                        provider.upper(), key[-4:], wait_s, reason,
                    )
                    await asyncio.sleep(wait_s)
                elif "RPD" in reason or "dnevna" in reason.lower():
                    syslog.debug(
                        "[rate_limiter] %s ...%s skip — %s",
                        provider.upper(), key[-4:], reason,
                    )
                    raise RuntimeError(f"Ključ nedostupan (RPD): {reason}")
                else:
                    syslog.debug(
                        "[rate_limiter] %s ...%s skip — %s",
                        provider.upper(), key[-4:], reason,
                    )
                    raise RuntimeError(f"Ključ nedostupan: {reason}")
        except ImportError:
            pass
        except RuntimeError:
            raise  # propagiraj dalje

    # IP-level per-provider semaphore — zaštita od burst-a prema istom provideru
    if provider:
        prov_sem = get_provider_semaphore(provider)
        await asyncio.to_thread(prov_sem.acquire)
        logger.debug("[rate_limiter] %s IP-semaphore zauzet (key=...%s)", provider.upper(), key[-4:])
        syslog.debug("[rate_limiter] %s IP-semaphore zauzet (key=...%s)", provider.upper(), key[-4:])

    sem = get_key_semaphore(key)
    await asyncio.to_thread(sem.acquire)
    logger.debug("[rate_limiter] key-semaphore zauzet: ...%s (%s)", key[-4:], (provider or "").upper())
    syslog.debug("[rate_limiter] key-semaphore zauzet: ...%s (%s)", key[-4:], (provider or "").upper())
    await _throttle_provider(provider, key=key)

    # Bilježi zahtjev u QuotaTracker
    if provider:
        try:
            from network.quota_tracker import quota_tracker
            quota_tracker.record_request(provider, key)
        except Exception:
            pass


def release_key(key: str, provider: str | None = None):
    sem = _key_semaphores.get(key)
    if sem is not None:
        sem.release()
        logger.debug("[rate_limiter] key-semaphore oslobođen: ...%s", key[-4:])
        syslog.debug("[rate_limiter] key-semaphore oslobođen: ...%s", key[-4:])
    if provider:
        prov_sem = _PROVIDER_SEMAPHORES.get(provider.upper())
        if prov_sem is not None:
            prov_sem.release()
            logger.debug("[rate_limiter] %s IP-semaphore oslobođen", provider.upper())
            syslog.debug("[rate_limiter] %s IP-semaphore oslobođen", provider.upper())
