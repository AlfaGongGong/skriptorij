# network/http_client.py — V12.0
#
# KOMPLETNI REWRITE pozivne logike po provajderu:
#
# GEMINI  — native endpoint (/v1beta/models/{model}:generateContent?key=...)
#            payload: {contents, systemInstruction, generationConfig}
#            response: {candidates[0].content.parts[0].text}
#            Free tier radi samo na native endpointu (OpenAI compat = limit 0)
#
# GEMMA   — Gemini native endpoint (same as Gemini)
#            Gemma 4 modeli na Google API-u s ?key= auth
#            Nema system role → merge u user poruku
#            payload: {contents, systemInstruction, generationConfig}
#            response: {candidates[0].content.parts[0].text}
#
# COHERE  — /v2/chat endpoint, OpenAI-compat messages format
#            response: {message.content[0].text}
#
# SVI OSTALI — standardni OpenAI-compat format
#            payload: {messages, model, temperature, max_tokens}
#            response: {choices[0].message.content}
#
# HTTP 500 — server greška (preopterećen model), ne rotiramo model nego ključ
# HTTP 429 — razlikujemo: ks.available=False → sljedeći ključ (ne rotiraj model)
# PROXY    — isključen (Webshare blokira Google; ostali provajderi blokiraju mobilni IP)

import asyncio
import logging
import random
import requests
import threading

from config.ai_config import (
    GEMMA_MODEL_POOL as _GEMMA_MODEL_POOL_FALLBACK,
    GOOGLE_MODEL_POOL as _GOOGLE_MODEL_POOL_FALLBACK,
)
from network.rate_limiter import (
    acquire_key,
    release_key,
    register_provider_runtime_limits,
)

logger = logging.getLogger(__name__)


class ContentFilterError(Exception):
    """Chunk blokiran content filterom (Azure/GitHub) — treba preskočiti chunk, ne mijenjati ključ."""

    pass


# ── Proxy — trenutno isključen ────────────────────────────────────────────────
def _get_next_proxy() -> dict | None:
    return None


# ── Google / Gemma model pool ─────────────────────────────────────────────────
GOOGLE_MODEL_POOL = _GOOGLE_MODEL_POOL_FALLBACK


def _get_google_model_pool() -> list[dict]:
    try:
        from network.model_discovery import get_dead_models

        dead = get_dead_models("GEMINI")
    except Exception:
        dead = frozenset()

    filtered = [m for m in _GOOGLE_MODEL_POOL_FALLBACK if m["model"] not in dead]
    return filtered if filtered else _GOOGLE_MODEL_POOL_FALLBACK


# ── Per-ključ model cache ─────────────────────────────────────────────────────
_key_model_cache: dict[str, int] = {}
_key_model_cache_lock = threading.Lock()


def _get_model_for_key(key: str, pool: list[dict] | None = None) -> str:
    if pool is None:
        pool = _get_google_model_pool()
    with _key_model_cache_lock:
        if key not in _key_model_cache:
            _key_model_cache[key] = 0
        idx = min(_key_model_cache[key], len(pool) - 1)
    return pool[idx]["model"]


def _rotate_model_for_key(key: str, pool: list[dict] | None = None) -> str | None:
    if pool is None:
        pool = _get_google_model_pool()
    with _key_model_cache_lock:
        start = _key_model_cache.get(key, 0)
        nxt = (start + 1) % len(pool)
        if nxt == 0:
            return None
        _key_model_cache[key] = nxt
    return pool[nxt]["model"]


def _reset_model_for_key(key: str, idx: int = 0) -> None:
    with _key_model_cache_lock:
        _key_model_cache[key] = idx if idx >= 0 else 0


# ── System role podrška ───────────────────────────────────────────────────────
_NO_SYSTEM_ROLE_PATTERNS = ("gemma",)


def _supports_system_role(model: str) -> bool:
    m = (model or "").lower()
    return not any(p in m for p in _NO_SYSTEM_ROLE_PATTERNS)


def _build_messages(sys_content: str | None, user_prompt: str, model: str) -> list:
    if not sys_content:
        return [{"role": "user", "content": user_prompt}]
    if not _supports_system_role(model):
        combined = f"[INSTRUKCIJE]\n{sys_content}\n\n[TEKST ZA OBRADU]\n{user_prompt}"
        return [{"role": "user", "content": combined}]
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": user_prompt},
    ]


# ── Gemini native payload/response ───────────────────────────────────────────
def _build_gemini_native_payload(
    sys_content: str | None, user_prompt: str, temperature: float, max_tokens: int
) -> dict:
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if sys_content:
        payload["systemInstruction"] = {"parts": [{"text": sys_content}]}
    return payload


def _extract_gemini_native(data: dict) -> str | None:
    if not data:
        return None
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            fb = data.get("promptFeedback", {})
            if fb.get("blockReason"):
                logger.warning("[GEMINI] Sadržaj blokiran: %s", fb.get("blockReason"))
            return None
        cand = candidates[0]
        finish = cand.get("finishReason", "")
        if finish == "SAFETY":
            logger.warning("[GEMINI] Odgovor blokiran (SAFETY filter)")
            return None
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        return text or None
    except (KeyError, IndexError, TypeError):
        return None


# ── Cohere v2 response ────────────────────────────────────────────────────────
def _extract_cohere(data: dict) -> str | None:
    if not data:
        return None
    try:
        parts = data["message"]["content"]
        if isinstance(parts, list):
            text = " ".join(
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
            return text or None
    except (KeyError, TypeError):
        pass
    return None


# ── Generički OpenAI-compat response ─────────────────────────────────────────
def _extract_openai_compat(data: dict) -> str | None:
    if not data:
        return None
    try:
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, str):
                return content.strip() or None
    except (KeyError, TypeError):
        pass
    return None


def _extract_content(provider: str, data: dict) -> str | None:
    prov = (provider or "").upper()
    if prov == "COHERE":
        return _extract_cohere(data)
    return _extract_openai_compat(data)


# ── Generički async HTTP POST ─────────────────────────────────────────────────
async def _async_http_post(
    self,
    url: str,
    headers: dict,
    json_payload: dict,
    prov: str,
    prov_upper: str,
    key: str,
    _proxy: dict | None = None,
) -> dict | None:
    await acquire_key(key, prov_upper)
    try:
        try:
            self.fleet.record_request(prov_upper, key)
        except Exception:
            pass

        try:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=json_payload,
                timeout=(15, 90),
                verify=True,
                proxies=_proxy,
            )
        except requests.exceptions.Timeout:
            self.log(f"[{prov_upper}] Timeout (90s)", "warning")
            # FIX: timeout treba evidentirati cooldown da rotation skoči na sljedeći ključ
            try:
                from network.quota_tracker import quota_tracker
                quota_tracker.set_key_cooldown(prov_upper, key, 30.0, "timeout 90s")
            except Exception:
                pass
            return None
        except Exception as e:
            self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:120]}", "error")
            return None

        resp_body = None
        if resp.status_code != 200:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = {"text": resp.text[:400]}

        try:
            self.fleet.analyze_response(
                prov, key, resp.status_code, resp.headers, resp_body
            )
        except Exception:
            pass

        if resp.status_code == 200:
            try:
                data = resp.json()
                register_provider_runtime_limits(prov_upper, resp.headers, data)
                return data
            except Exception:
                self.log(
                    f"[{prov_upper}] Neispravan JSON u odgovoru (HTTP 200)", "error"
                )
                return None

        elif resp.status_code in (429, 425):
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
            body_preview = str(resp_body)[:300] if resp_body else "nema body-ja"
            self.log(
                f"[{prov_upper}] HTTP 429 — cooldown postavlja quota_tracker | {body_preview}",
                "warning",
            )
            # NE spavamo ovdje — analyze_response/quota_tracker vec postavlja cooldown
            # na kljuc. Sleep ovdje blokira worker, pa kad se probudi svi cekaci
            # prolaze odjednom (burst). Pravilni throttle je u acquire_key/rate_limiter.
            return None

        elif resp.status_code == 500:
            self.log(
                f"[{prov_upper}] HTTP 500 (server greška) — biram drugi ključ",
                "warning",
            )
            await asyncio.sleep(2.0)
            return None

        elif resp.status_code in (401, 402, 403, 412):
            self.log(
                f"[{prov_upper}] HTTP {resp.status_code} — ključ nevažeći", "error"
            )
            return None

        elif resp.status_code == 404:
            model_used = (
                (json_payload or {}).get("model", "")
                if isinstance(json_payload, dict)
                else ""
            )
            if model_used:
                try:
                    from network.model_discovery import invalidate_cached_model

                    invalidate_cached_model(prov_upper, model_used)
                except Exception:
                    pass
            self.log(f"[{prov_upper}] HTTP 404 — model ne postoji", "warning")
            return None

        elif resp.status_code == 400:
            err = str(resp_body)[:300] if resp_body else resp.text[:300]
            if any(
                kw in err.lower()
                for kw in (
                    "content management policy",
                    "content_filter",
                    "response was filtered",
                )
            ):
                self.log(
                    f"[{prov_upper}] HTTP 400 — Azure content filter, preskačem chunk",
                    "warning",
                )
                raise ContentFilterError(
                    f"[{prov_upper}] sadržaj blokiran content filterom"
                )
            self.log(f"[{prov_upper}] HTTP 400: {err}", "warning")
            return None

        else:
            self.log(f"[{prov_upper}] HTTP {resp.status_code}", "warning")
            return None

    finally:
        release_key(key, prov_upper)


# ── Gemini poziv (native endpoint) ───────────────────────────────────────────
async def _call_gemini_with_full_rotation(
    self,
    sys_content,
    user_prompt,
    opt_temp,
    max_tokens=2400,
    preferred_model: str = None,
):
    from network.provider_urls import get_gemini_url

    # Ako su svi ključevi privremeno u min_gap/kratkom cooldownu — sačekaj najkraćeg
    # umjesto da odmah odustanemo. "Nema dostupnih" zbog min_gap nije greška — samo čekanje.
    _all_ks = self.fleet.fleet.get("GEMINI", [])
    keys_list = [ks for ks in _all_ks if ks.available]
    if not keys_list and _all_ks:
        from network.quota_tracker import quota_tracker

        waits = []
        for ks in _all_ks:
            ok, reason = quota_tracker.is_key_available("GEMINI", ks.key)
            if not ok:
                import re as _re

                # Kratki cooldown (min_gap ili RPM cooldown ≤60s) — vrijedi čekati
                m = _re.search(r"([\d.]+)s", reason)
                secs = float(m.group(1)) if m else 99999.0
                if secs <= 60.0:
                    waits.append(secs)
        if waits:
            wait_s = min(waits) + 0.5
            self.log(
                f"[GEMINI] Svi ključevi u kratkom cooldownu — čekam {wait_s:.1f}s",
                "warning",
            )
            await asyncio.sleep(wait_s)
            keys_list = [ks for ks in _all_ks if ks.available]
    if not keys_list:
        self.log("[GEMINI] Nema dostupnih ključeva", "warning")
        return None, None

    keys_list.sort(key=lambda ks: ks.success_rate, reverse=True)
    pool = _get_google_model_pool()

    for ks in keys_list:
        key = ks.key

        if preferred_model and preferred_model in {m["model"] for m in pool}:
            current_model = preferred_model
            for i, m in enumerate(pool):
                if m["model"] == preferred_model:
                    with _key_model_cache_lock:
                        _key_model_cache[key] = i
                    break
        else:
            current_model = _get_model_for_key(key, pool)

        tried: set[str] = set()

        for _ in range(len(pool) + 1):
            if current_model in tried:
                break
            tried.add(current_model)

            url = f"{get_gemini_url(current_model)}?key={key}"
            headers = {"Content-Type": "application/json"}
            payload = _build_gemini_native_payload(
                sys_content, user_prompt, opt_temp, max_tokens
            )

            data = await _async_http_post(
                self, url, headers, payload, "GEMINI", "GEMINI", key, _proxy=None
            )

            if data is not None:
                content = _extract_gemini_native(data)
                if content:
                    return content, f"GEMINI-{current_model}"

            if not ks.available:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} u cooldownu — preskačem na sljedeći ključ",
                    "warning",
                )
                break

            next_model = _rotate_model_for_key(key, pool)
            if next_model is None:
                _reset_model_for_key(key)
                self.log(
                    f"[GEMINI] Svi modeli iscrpljeni za ključ ...{key[-4:]}", "warning"
                )
                try:
                    from network.model_discovery import trigger_rediscover_background

                    trigger_rediscover_background("GEMINI", key)
                except Exception:
                    pass
                break

            self.log(f"[GEMINI] {current_model} → {next_model}", "warning")
            current_model = next_model
            await asyncio.sleep(0.5)

    # Nakon potpune iscrpljenosti vrati svaki ključ na prvi model iz statičkog
    # poola, tako da sljedeći ciklus opet krene od primarnog stabilnog modela.
    for ks in keys_list:
        _reset_model_for_key(ks.key)

    self.log("[GEMINI] Svi ključevi i modeli iscrpljeni", "error")
    return None, None


# ── Gemma poziv (Gemini native endpoint) ──────────────────────────────────────
# FIX bugs #1-5, #9-10: Gemma 4 modeli idu na Gemini native endpoint (ne Together.AI).
# Auth: ?key={key} u URL-u (ne Bearer header)
# Payload: contents/systemInstruction format (ne OpenAI messages)
# Model string: gemma-4-26b-it (ne google/gemma-4-26b-it)
# Ključevi: GEMINI fleet (ne GEMMA fleet)
# Response: _extract_gemini_native (ne _extract_openai_compat)
# Model rotation: rotira model pri 429 (kao Gemini)
async def _call_gemma_with_rotation(
    self,
    sys_content,
    user_prompt,
    opt_temp,
    max_tokens=2400,
    preferred_model: str = None,
):
    from network.provider_urls import get_gemini_url
    from network.quota_tracker import quota_tracker

    # Koristi GEMINI ključeve (Gemma 4 je na Google API-u)
    _all_ks = self.fleet.fleet.get("GEMINI", [])
    keys_list = []
    for ks in _all_ks:
        ok, _reason = quota_tracker.is_key_available("GEMMA", ks.key)
        if ok:
            keys_list.append(ks)
    if not keys_list and _all_ks:
        waits = []
        for ks in _all_ks:
            ok, reason = quota_tracker.is_key_available("GEMMA", ks.key)
            if not ok:
                import re as _re

                m = _re.search(r"([\d.]+)s", reason)
                secs = float(m.group(1)) if m else 99999.0
                if secs <= 60.0:
                    waits.append(secs)
        if waits:
            wait_s = min(waits) + 0.5
            self.log(
                f"[GEMMA] Svi ključevi u kratkom cooldownu — čekam {wait_s:.1f}s",
                "warning",
            )
            await asyncio.sleep(wait_s)
            keys_list = []
            for ks in _all_ks:
                ok, _reason = quota_tracker.is_key_available("GEMMA", ks.key)
                if ok:
                    keys_list.append(ks)
    if not keys_list:
        self.log("[GEMMA] Nema dostupnih GEMINI ključeva", "warning")
        return None, None

    keys_list.sort(key=lambda ks: ks.success_rate, reverse=True)
    pool = _GEMMA_MODEL_POOL_FALLBACK

    for ks in keys_list:
        key = ks.key

        if preferred_model and preferred_model in {m["model"] for m in pool}:
            current_model = preferred_model
        else:
            current_model = pool[0]["model"]

        tried: set[str] = set()

        for _ in range(len(pool) + 1):
            if current_model in tried:
                break
            tried.add(current_model)

            url = f"{get_gemini_url(current_model)}?key={key}"
            headers = {"Content-Type": "application/json"}
            #  — Gemma 4 thinking model, isključi za bulk prevod
            payload = _build_gemini_native_payload(
                sys_content,
                user_prompt,
                opt_temp,
                max_tokens,
            )

            data = await _async_http_post(
                self, url, headers, payload, "GEMMA", "GEMINI", key, _proxy=None
            )

            if data is not None:
                content = _extract_gemini_native(data)
                if content:
                    return content, f"GEMMA-{current_model}"

            # FIX: timeout ne postavlja GEMMA cooldown, pa provjeri i ks.available
            # (isti pattern kao u _call_gemini_with_full_rotation)
            if not ks.available:
                self.log(
                    f"[GEMMA] Ključ ...{key[-4:]} nedostupan (timeout/429) — preskačem na sljedeći ključ",
                    "warning",
                )
                break

            key_ok, _reason = quota_tracker.is_key_available("GEMMA", key)
            if not key_ok:
                self.log(
                    f"[GEMMA] Ključ ...{key[-4:]} u cooldownu — preskačem na sljedeći ključ",
                    "warning",
                )
                break

            # Model rotation pri 429 (bug #9 fix)
            next_idx = None
            for i, m in enumerate(pool):
                if m["model"] == current_model:
                    next_idx = i + 1
                    break
            if next_idx is not None and next_idx < len(pool):
                next_model = pool[next_idx]["model"]
                self.log(f"[GEMMA] {current_model} → {next_model}", "warning")
                current_model = next_model
                await asyncio.sleep(0.5)
            else:
                self.log(
                    f"[GEMMA] Svi modeli iscrpljeni za ključ ...{key[-4:]}", "warning"
                )
                break

    self.log("[GEMMA] Svi ključevi i modeli iscrpljeni", "error")
    return None, None


# ── Generički single-provider poziv ──────────────────────────────────────────
async def _call_single_provider(
    self, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=2400
):
    await asyncio.sleep(random.uniform(0.3, 1.5))

    if prov_upper == "GEMINI":
        return await _call_gemini_with_full_rotation(
            self,
            sys_content,
            user_prompt,
            opt_temp,
            max_tokens,
            preferred_model=model,
        )

    if prov_upper == "GEMMA":
        return await _call_gemma_with_rotation(
            self,
            sys_content,
            user_prompt,
            opt_temp,
            max_tokens,
            preferred_model=model,
        )

    key = self.fleet.get_best_key(prov_upper)
    if not key:
        return None, None

    from network.provider_urls import get_url

    url = get_url(prov_upper)

    messages = _build_messages(sys_content, user_prompt, model)
    payload = {
        "model": model,
        "temperature": opt_temp,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    data = await _async_http_post(
        self, url, headers, payload, prov_upper, prov_upper, key
    )
    if not data:
        return None, None

    content = _extract_content(prov_upper, data)
    if content:
        return content, f"{prov_upper}-{model}"
    return None, None


# ── Blocking API poziv (za WorkerV2) ─────────────────────────────────────────
def api_call(
    provider: str,
    model: str,
    api_key: str,
    system: str,
    user: str,
    temperature: float = 0.5,
    max_tokens: int = 2400,
    timeout: int = 90,
) -> str | None:
    from network.provider_urls import get_url, get_gemini_url
    from network.rate_limiter import get_key_semaphore, get_provider_semaphore
    import time as _time

    prov_upper = provider.upper()

    if prov_upper in ("GEMINI", "GEMMA"):
        url = f"{get_gemini_url(model)}?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = _build_gemini_native_payload(system, user, temperature, max_tokens)
    else:
        url = get_url(prov_upper)
        messages = _build_messages(system, user, model)
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    prov_sem = get_provider_semaphore(prov_upper)
    key_sem = get_key_semaphore(api_key)
    prov_sem.acquire()
    key_sem.acquire()
    try:
        # Poštivanje min_gap iz QuotaTracker — kritično za Gemini free tier
        # Bez ovoga: api_call() šalje zahtjeve svake 0.3-1.2s bez obzira na RPM limit
        try:
            from network.quota_tracker import quota_tracker
            import re as _re

            ok, reason = quota_tracker.is_key_available(prov_upper, api_key)
            if not ok:
                _m = _re.search(r"([\d.]+)s", reason)
                wait_s = float(_m.group(1)) if _m else 5.0
                wait_s = min(wait_s, 60.0)
                logger.debug(
                    "[api_call] %s ...%s min_gap cekanje %.1fs",
                    prov_upper,
                    api_key[-4:],
                    wait_s,
                )
                _time.sleep(wait_s)
            quota_tracker.record_request(prov_upper, api_key)
        except Exception:
            pass
        _time.sleep(random.uniform(0.5, 2.0))  # humanizovani jitter
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            logger.warning("[api_call] %s mrežna greška: %s", prov_upper, str(e)[:120])
            return None

        if resp.status_code == 429:
            ra_raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            try:
                ra = float(ra_raw) if ra_raw else 10.0
            except ValueError:
                ra = 10.0
            _time.sleep(min(ra, 120.0) + random.uniform(0.5, 2.0))
            return None

        if resp.status_code != 200:
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        if prov_upper in ("GEMINI", "GEMMA"):
            return _extract_gemini_native(data)
        return _extract_content(prov_upper, data)

    finally:
        key_sem.release()
        prov_sem.release()
