"""network/rate_limiter.py

Per-ključ i per-provider throttling i semafor zaštita.

Semafori:
  - Per-key: threading.Semaphore (MAX_CONCURRENT_PER_KEY=1) — process-wide, cross-thread
  - Per-provider: threading.Semaphore (MAX_CONCURRENT_PER_PROVIDER=2) — IP-level zaštita

Throttling:
  - Per-key min_gap: čeka razliku od zadnjeg stvarnog slanja (ne rezervacije)
  - Provider-level backoff: globalni cooldown nakon 429
  - Dinamički gap: EWMA prilagodba na osnovu opaženih RPM/TPM limita iz headera
"""

import asyncio
import logging
import random
import threading
import time

from config.system_logger import syslog

logger = logging.getLogger(__name__)

_PROVIDER_LOCKS: dict = {}
_LAST_CALLS: dict = {}
_LAST_CALLS_KEY: dict = {}
_LAST_CALLS_KEY_LOCK = threading.Lock()
_PROVIDER_COOLDOWN_UNTIL: dict = {}
_PROVIDER_DYNAMIC_GAP: dict = {}

try:
    from config.ai_config import get_min_gap as _get_provider_min_gap

    def _provider_gap(prov: str) -> float:
        return _get_provider_min_gap(prov)
except ImportError:
    _PROVIDER_MIN_GAP_FALLBACK = {
        "GEMINI": 5.0,
        "GROQ": 2.5,
        "CEREBRAS": 2.5,
        "SAMBANOVA": 7.5,
        "MISTRAL": 62.0,
        "COHERE": 3.75,
        "OPENROUTER": 4.0,
        "GITHUB": 7.5,
        "TOGETHER": 3.75,
        "FIREWORKS": 3.75,
        "CHUTES": 7.5,
        "HUGGINGFACE": 8.6,
        "KLUSTER": 5.0,
        "GEMMA": 7.5,
    }

    def _provider_gap(prov: str) -> float:
        return _PROVIDER_MIN_GAP_FALLBACK.get(prov.upper(), 5.0)


_RPM_THROTTLE_MULTIPLIER = 1.8
_JITTER_MIN = 1.0
_JITTER_MAX = 3.0


async def _ensure_provider_lock(prov: str) -> asyncio.Lock:
    current_loop_id = id(asyncio.get_running_loop())
    entry = _PROVIDER_LOCKS.get(prov)
    if entry is not None:
        stored_loop_id, lock = entry
        if current_loop_id == stored_loop_id:
            return lock
    lock = asyncio.Lock()
    _PROVIDER_LOCKS[prov] = (current_loop_id, lock)
    return lock


def register_provider_backoff(provider: str | None, retry_after: float | None) -> None:
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
        logger.warning(
            "[rate_limiter] %s backoff: %.1fs (do %s)",
            prov,
            ra,
            time.strftime("%H:%M:%S", time.localtime(until)),
        )
        syslog.warning(
            "[rate_limiter] %s backoff: %.1fs (do %s)",
            prov,
            ra,
            time.strftime("%H:%M:%S", time.localtime(until)),
        )

    try:
        from network.quota_tracker import quota_tracker

        quota_tracker.set_provider_cooldown(
            prov, ra, reason=f"register_provider_backoff {ra:.0f}s"
        )
    except Exception as e:
        logger.debug("[rate_limiter] quota_tracker propagacija backoffa: %s", e)


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

    usage_meta = body.get("usageMetadata")
    if isinstance(usage_meta, dict):
        total = _to_float(usage_meta.get("totalTokenCount"))
        if total and total > 0:
            return total
        prompt = _to_float(usage_meta.get("promptTokenCount")) or 0.0
        candidates = _to_float(usage_meta.get("candidatesTokenCount")) or 0.0
        if prompt > 0 or candidates > 0:
            return prompt + candidates

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

    meta = body.get("meta")
    if isinstance(meta, dict):
        tokens = meta.get("tokens")
        if isinstance(tokens, dict):
            inp = _to_float(tokens.get("input_tokens")) or 0.0
            out = _to_float(tokens.get("output_tokens")) or 0.0
            if inp > 0 or out > 0:
                return inp + out

    return None


def register_provider_runtime_limits(
    provider: str | None, headers=None, body=None
) -> None:
    if not provider:
        return
    prov = provider.upper()

    rpm_limit = _header_float(
        headers,
        [
            "x-ratelimit-limit-requests",
            "ratelimit-limit",
            "x-limit-requests",
        ],
    )
    tpm_limit = _header_float(
        headers,
        [
            "x-ratelimit-limit-tokens",
            "ratelimit-limit-tokens",
            "x-limit-tokens",
        ],
    )
    token_cost = _extract_total_tokens(body)

    rpm_gap = (60.0 / rpm_limit) if (rpm_limit and rpm_limit > 0) else 0.0
    tpm_gap = (
        (60.0 * token_cost / tpm_limit)
        if (tpm_limit and tpm_limit > 0 and token_cost and token_cost > 0)
        else 0.0
    )

    observed_gap = max(rpm_gap, tpm_gap, 0.0)
    if observed_gap <= 0:
        return

    observed_gap = min(observed_gap * 1.15, 20.0)

    prev = _PROVIDER_DYNAMIC_GAP.get(prov, 0.0)
    if prev <= 0:
        _PROVIDER_DYNAMIC_GAP[prov] = observed_gap
        logger.info(
            "[rate_limiter] %s: dinamički gap inicijaliziran na %.2fs",
            prov,
            observed_gap,
        )
    else:
        new_gap = (0.70 * prev) + (0.30 * observed_gap)
        _PROVIDER_DYNAMIC_GAP[prov] = new_gap
        if abs(new_gap - prev) > 0.5:
            logger.debug(
                "[rate_limiter] %s: dinamički gap %.2fs→%.2fs", prov, prev, new_gap
            )


import threading as _threading

_key_semaphores: dict[str, _threading.Semaphore] = {}
_key_semaphores_lock = _threading.Lock()
MAX_CONCURRENT_PER_KEY = 1

_PROVIDER_SEMAPHORES: dict[str, _threading.Semaphore] = {}
_PROVIDER_SEMAPHORES_LOCK = _threading.Lock()
MAX_CONCURRENT_PER_PROVIDER = 2


def get_key_semaphore(key: str) -> _threading.Semaphore:
    with _key_semaphores_lock:
        if key not in _key_semaphores:
            _key_semaphores[key] = _threading.Semaphore(MAX_CONCURRENT_PER_KEY)
        return _key_semaphores[key]


def get_provider_semaphore(provider: str) -> _threading.Semaphore:
    prov = provider.upper()
    with _PROVIDER_SEMAPHORES_LOCK:
        if prov not in _PROVIDER_SEMAPHORES:
            _PROVIDER_SEMAPHORES[prov] = _threading.Semaphore(
                MAX_CONCURRENT_PER_PROVIDER
            )
        return _PROVIDER_SEMAPHORES[prov]


async def _throttle_provider(provider: str | None, key: str | None = None) -> None:
    if not provider:
        return

    prov = provider.upper()

    provider_cooldown_until = _PROVIDER_COOLDOWN_UNTIL.get(prov, 0.0)
    now = time.time()
    if provider_cooldown_until > now:
        wait = min(provider_cooldown_until - now, 120.0)
        if wait > 0:
            logger.info("[rate_limiter] %s cooldown aktivan — čekam %.1fs", prov, wait)
            await asyncio.sleep(wait)

    base_gap = _provider_gap(prov)
    dynamic_gap = _PROVIDER_DYNAMIC_GAP.get(prov, 0.0)
    base_gap = max(base_gap, dynamic_gap)

    if key:
        with _LAST_CALLS_KEY_LOCK:
            last_sent = _LAST_CALLS_KEY.get(key, 0.0)
    else:
        last_sent = _LAST_CALLS.get(prov, 0.0)

    gap = base_gap + random.uniform(0.5, 1.5)
    wait = (last_sent + gap) - time.time()

    if wait > 0:
        logger.debug(
            "[rate_limiter] %s ...%s throttle %.2fs (gap=%.1f+jitter)",
            prov,
            (key or "")[-4:],
            wait,
            base_gap,
        )
        await asyncio.sleep(wait)

    now_sending = time.time()
    if key:
        with _LAST_CALLS_KEY_LOCK:
            _LAST_CALLS_KEY[key] = now_sending
    else:
        _LAST_CALLS[prov] = now_sending


async def acquire_key(key: str, provider: str | None = None):
    if provider:
        try:
            from network.quota_tracker import quota_tracker

            ok, reason = quota_tracker.is_key_available(provider, key)
            if not ok:
                if "min_gap" in reason or (
                    "cooldown" in reason and "čekanje" in reason
                ):
                    import re as _re

                    match = _re.search(r"([\d.]+)s", reason)
                    wait_s = min(float(match.group(1)) if match else 5.0, 15.0)
                    syslog.debug(
                        "[rate_limiter] %s ...%s čekam %.1fs — %s",
                        provider.upper(),
                        key[-4:],
                        wait_s,
                        reason,
                    )
                    await asyncio.sleep(wait_s)
                elif "RPD" in reason or "dnevna" in reason.lower():
                    syslog.debug(
                        "[rate_limiter] %s ...%s skip — %s",
                        provider.upper(),
                        key[-4:],
                        reason,
                    )
                    raise RuntimeError(f"Ključ nedostupan (RPD): {reason}")
                else:
                    syslog.debug(
                        "[rate_limiter] %s ...%s skip — %s",
                        provider.upper(),
                        key[-4:],
                        reason,
                    )
                    raise RuntimeError(f"Ključ nedostupan: {reason}")
        except ImportError:
            pass
        except RuntimeError:
            raise

    # Throttle PRIJE semaphore — ne blokiramo ostale ključeve dok čekamo gap/cooldown
    await _throttle_provider(provider, key=key)

    if provider:
        prov_sem = get_provider_semaphore(provider)
        await asyncio.to_thread(prov_sem.acquire)
        logger.debug(
            "[rate_limiter] %s IP-semaphore zauzet (key=...%s)",
            provider.upper(),
            key[-4:],
        )
        syslog.debug(
            "[rate_limiter] %s IP-semaphore zauzet (key=...%s)",
            provider.upper(),
            key[-4:],
        )

    sem = get_key_semaphore(key)
    await asyncio.to_thread(sem.acquire)
    logger.debug(
        "[rate_limiter] key-semaphore zauzet: ...%s (%s)",
        key[-4:],
        (provider or "").upper(),
    )
    syslog.debug(
        "[rate_limiter] key-semaphore zauzet: ...%s (%s)",
        key[-4:],
        (provider or "").upper(),
    )

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
