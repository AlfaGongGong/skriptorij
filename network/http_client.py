# network/http_client.py — V11.0
#
# KOMPLETNI REWRITE pozivne logike po provajderu:
#
# GEMINI  — native endpoint (/v1beta/models/{model}:generateContent?key=...)
#            payload: {contents, systemInstruction, generationConfig}
#            response: {candidates[0].content.parts[0].text}
#            Free tier radi samo na native endpointu (OpenAI compat = limit 0)
#
# GEMMA   — Together.AI OpenAI-compat endpoint
#            Nema system role → merge u user poruku
#            payload: standardni OpenAI {messages, model, temperature, max_tokens}
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

from network.rate_limiter import (
    acquire_key,
    release_key,
    register_provider_backoff,
    register_provider_runtime_limits,
)

logger = logging.getLogger(__name__)

# ── Proxy — trenutno isključen ────────────────────────────────────────────────
# Webshare datacenter proksiji blokiraju Google (Max retries exceeded).
# Ostali provajderi (Groq, Mistral...) blokiraju mobilni IP direktno.
# Rješenje: residential proksiji (Smartproxy/Oxylabs) kad se nabave.
def _get_next_proxy() -> dict | None:
    return None


# ── Google / Gemma model pool ─────────────────────────────────────────────────
# Gemini modeli → native Google endpoint
# Gemma modeli  → Together.AI endpoint (drugačiji API ključevi!)
_GOOGLE_MODEL_POOL_FALLBACK = [
    {"model": "gemini-2.0-flash",      "rpm": 15, "rpd": 1500},
    {"model": "gemini-2.5-flash",      "rpm": 10, "rpd": 500},
    {"model": "gemini-2.0-flash-lite", "rpm": 30, "rpd": 1500},
]
_GEMMA_MODEL_POOL_FALLBACK = [
    {"model": "google/gemma-4-9b-it",  "rpm": 15, "rpd": 1000},
    {"model": "google/gemma-3-27b-it", "rpm": 10, "rpd": 500},
]
GOOGLE_MODEL_POOL = _GOOGLE_MODEL_POOL_FALLBACK


def _get_google_model_pool() -> list[dict]:
    fallback_by_id = {m["model"]: m for m in _GOOGLE_MODEL_POOL_FALLBACK}
    try:
        from network.model_discovery import get_cached_model_list, get_dead_models
        dead = get_dead_models("GEMINI")
        discovered = get_cached_model_list("GEMINI")
        if discovered:
            pool = [fallback_by_id[mid] for mid in discovered
                    if mid in fallback_by_id and mid not in dead]
            existing = {m["model"] for m in pool}
            for fb in _GOOGLE_MODEL_POOL_FALLBACK:
                if fb["model"] not in existing and fb["model"] not in dead:
                    pool.append(fb)
            return pool if pool else _GOOGLE_MODEL_POOL_FALLBACK
        if dead:
            filtered = [m for m in _GOOGLE_MODEL_POOL_FALLBACK if m["model"] not in dead]
            return filtered if filtered else _GOOGLE_MODEL_POOL_FALLBACK
    except Exception:
        pass
    return _GOOGLE_MODEL_POOL_FALLBACK


# ── Per-ključ model cache (koji model je aktivan za koji ključ) ───────────────
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


# ── System role podrška ───────────────────────────────────────────────────────
_NO_SYSTEM_ROLE_PATTERNS = ("gemma",)


def _supports_system_role(model: str) -> bool:
    m = (model or "").lower()
    return not any(p in m for p in _NO_SYSTEM_ROLE_PATTERNS)


def _build_messages(sys_content: str | None, user_prompt: str, model: str) -> list:
    """OpenAI-compat messages lista. Gemma: spoji system+user u jednu poruku."""
    if not sys_content:
        return [{"role": "user", "content": user_prompt}]
    if not _supports_system_role(model):
        combined = f"[INSTRUKCIJE]\n{sys_content}\n\n[TEKST ZA OBRADU]\n{user_prompt}"
        return [{"role": "user", "content": combined}]
    return [
        {"role": "system", "content": sys_content},
        {"role": "user",   "content": user_prompt},
    ]


# ── Gemini native payload/response ───────────────────────────────────────────
def _build_gemini_native_payload(sys_content: str | None, user_prompt: str,
                                  temperature: float, max_tokens: int) -> dict:
    """
    Native Gemini format:
      contents: [{role: user, parts: [{text: ...}]}]
      systemInstruction: {parts: [{text: ...}]}  (opcionalno)
      generationConfig: {temperature, maxOutputTokens}
    """
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
    """
    Native Gemini response:
      candidates[0].content.parts[0].text
    Provjeri finishReason — SAFETY znači blokiran sadržaj.
    """
    if not data:
        return None
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            # promptFeedback blok — sigurnosni filter
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
    """
    Cohere /v2/chat response:
      message.content[0].text
    """
    if not data:
        return None
    try:
        parts = data["message"]["content"]
        if isinstance(parts, list):
            text = " ".join(
                p.get("text", "") for p in parts
                if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
            return text or None
    except (KeyError, TypeError):
        pass
    return None


# ── Generički OpenAI-compat response ─────────────────────────────────────────
def _extract_openai_compat(data: dict) -> str | None:
    """choices[0].message.content"""
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
    """Router za response parsiranje po provajderu."""
    prov = (provider or "").upper()
    if prov == "COHERE":
        return _extract_cohere(data)
    # Gemini native parsira se odvojeno u _call_gemini_with_full_rotation
    return _extract_openai_compat(data)


# ── Generički async HTTP POST ─────────────────────────────────────────────────
async def _async_http_post(self, url: str, headers: dict, json_payload: dict,
                            prov: str, prov_upper: str, key: str,
                            _proxy: dict | None = None) -> dict | None:
    """
    Generički async HTTP POST s rate limiting i error handling.

    Vraća parsed JSON dict pri HTTP 200, None u svim ostalim slučajevima.
    Fleet se ažurira (analyze_response) za sve statuse.
    """
    await acquire_key(key, prov_upper)
    try:
        try:
            self.fleet.record_request(prov_upper, key)
        except Exception:
            pass

        try:
            resp = await asyncio.to_thread(
                requests.post, url,
                headers=headers,
                json=json_payload,
                timeout=(15, 90),
                verify=True,
                proxies=_proxy,
            )
        except requests.exceptions.Timeout:
            self.log(f"[{prov_upper}] Timeout (90s)", "warning")
            return None
        except Exception as e:
            self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:120]}", "error")
            return None

        # Parsiraj body za ne-200 statuse (za analyze_response i logiranje)
        resp_body = None
        if resp.status_code != 200:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = {"text": resp.text[:400]}

        try:
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers, resp_body)
        except Exception:
            pass

        # ── 200 OK ───────────────────────────────────────────────────────────
        if resp.status_code == 200:
            try:
                data = resp.json()
                register_provider_runtime_limits(prov_upper, resp.headers, data)
                return data
            except Exception:
                self.log(f"[{prov_upper}] Neispravan JSON u odgovoru (HTTP 200)", "error")
                return None

        # ── 429 Rate limit / kvota ────────────────────────────────────────────
        elif resp.status_code in (429, 425):
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
            ra_raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            try:
                retry_after = float(ra_raw) if ra_raw else None
            except ValueError:
                retry_after = None

            if retry_after and retry_after > 3600:
                self.log(f"[{prov_upper}] Dnevna kvota iscrpljena — biram drugi ključ", "warning")
            else:
                wait = min(retry_after or 4.0, 120.0) + random.uniform(0.5, 2.0)
                self.log(f"[{prov_upper}] HTTP 429 — pauza {wait:.1f}s, biram drugi ključ", "warning")
                await asyncio.sleep(wait)
            return None

        # ── 500 Server greška (preopterećen model, ne naša greška) ───────────
        elif resp.status_code == 500:
            self.log(f"[{prov_upper}] HTTP 500 (server greška) — biram drugi ključ", "warning")
            await asyncio.sleep(2.0)
            return None

        # ── 401/402/403/412 Nevažeći ključ ───────────────────────────────────
        elif resp.status_code in (401, 402, 403, 412):
            self.log(f"[{prov_upper}] HTTP {resp.status_code} — ključ nevažeći", "error")
            return None

        # ── 404 Model ne postoji ──────────────────────────────────────────────
        elif resp.status_code == 404:
            model_used = (json_payload or {}).get("model", "") if isinstance(json_payload, dict) else ""
            if model_used:
                try:
                    from network.model_discovery import invalidate_cached_model
                    invalidate_cached_model(prov_upper, model_used)
                except Exception:
                    pass
            self.log(f"[{prov_upper}] HTTP 404 — model ne postoji", "warning")
            return None

        # ── 400 Bad request ───────────────────────────────────────────────────
        elif resp.status_code == 400:
            err = str(resp_body)[:200] if resp_body else resp.text[:200]
            self.log(f"[{prov_upper}] HTTP 400: {err}", "warning")
            return None

        # ── Ostali statusi ────────────────────────────────────────────────────
        else:
            self.log(f"[{prov_upper}] HTTP {resp.status_code}", "warning")
            return None

    finally:
        release_key(key, prov_upper)


# ── Gemini poziv (native endpoint) ───────────────────────────────────────────
async def _call_gemini_with_full_rotation(
    self, sys_content, user_prompt, opt_temp, max_tokens=2400,
    preferred_model: str = None,
):
    """
    Poziva Gemini API koristeći native endpoint.

    URL format:  /v1beta/models/{model}:generateContent?key={api_key}
    Auth:        query parametar ?key= (NE Authorization header)
    Payload:     native Gemini format (contents, systemInstruction, generationConfig)
    Response:    candidates[0].content.parts[0].text

    Rotacija:
      - 429 / 500 / ks.available=False → sljedeći ključ (ne rotiraj model)
      - 404 / timeout / mrežna greška  → rotiraj model, pa sljedeći ključ
    """
    from network.provider_urls import get_gemini_url

    keys_list = [ks for ks in self.fleet.fleet.get("GEMINI", []) if ks.available]
    if not keys_list:
        self.log("[GEMINI] Nema dostupnih ključeva", "warning")
        return None, None

    keys_list.sort(key=lambda ks: ks.success_rate, reverse=True)
    pool = _get_google_model_pool()

    for ks in keys_list:
        key = ks.key

        # Odredi početni model
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

            # Native endpoint: model u URL-u, ključ kao query param
            url = f"{get_gemini_url(current_model)}?key={key}"
            headers = {"Content-Type": "application/json"}
            payload = _build_gemini_native_payload(sys_content, user_prompt, opt_temp, max_tokens)

            data = await _async_http_post(
                self, url, headers, payload, "GEMINI", "GEMINI", key, _proxy=None
            )

            if data is not None:
                content = _extract_gemini_native(data)
                if content:
                    return content, f"GEMINI-{current_model}"
                # data vraćen ali prazan sadržaj (SAFETY filter itd.) → sljedeći model
            
            # Ako je ključ ušao u cooldown (429/kvota/500) → sljedeći ključ
            if not ks.available:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} u cooldownu — preskačem na sljedeći ključ",
                    "warning",
                )
                break

            # 404 / timeout / mrežna greška → rotiraj model
            next_model = _rotate_model_for_key(key, pool)
            if next_model is None:
                self.log(f"[GEMINI] Svi modeli iscrpljeni za ključ ...{key[-4:]}", "warning")
                try:
                    from network.model_discovery import trigger_rediscover_background
                    trigger_rediscover_background("GEMINI", key)
                except Exception:
                    pass
                break

            self.log(f"[GEMINI] {current_model} → {next_model}", "warning")
            current_model = next_model
            await asyncio.sleep(0.5)

    self.log("[GEMINI] Svi ključevi i modeli iscrpljeni", "error")
    return None, None


# ── Gemma poziv (Together.AI) ─────────────────────────────────────────────────
async def _call_gemma_with_rotation(
    self, sys_content, user_prompt, opt_temp, max_tokens=2400,
    preferred_model: str = None,
):
    """
    Poziva Gemma modele putem Together.AI.

    Gemma NE podržava system role → _build_messages spaja u user poruku.
    Together.AI koristi standardni OpenAI-compat format.
    API ključevi: GEMMA sekcija u dev_api.json (odvojeni od GEMINI ključeva).
    """
    from network.provider_urls import get_url
    url = get_url("GEMMA")

    keys_list = [ks for ks in self.fleet.fleet.get("GEMMA", []) if ks.available]
    if not keys_list:
        self.log("[GEMMA] Nema dostupnih ključeva", "warning")
        return None, None

    pool = _GEMMA_MODEL_POOL_FALLBACK
    model = preferred_model or pool[0]["model"]

    for ks in keys_list:
        key = ks.key
        # Gemma ne podržava system role — _build_messages to zna
        messages = _build_messages(sys_content, user_prompt, model)
        payload = {
            "model":       model,
            "temperature": opt_temp,
            "max_tokens":  max_tokens,
            "messages":    messages,
        }
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {key}",
        }
        data = await _async_http_post(
            self, url, headers, payload, "GEMMA", "GEMMA", key
        )
        if data:
            content = _extract_openai_compat(data)
            if content:
                return content, f"GEMMA-{model}"
        if not ks.available:
            continue

    self.log("[GEMMA] Svi ključevi iscrpljeni", "error")
    return None, None


# ── Generički single-provider poziv (svi ostali) ─────────────────────────────
async def _call_single_provider(
    self, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=2400
):
    """
    Standardni OpenAI-compat poziv za sve providere osim Gemini i Gemma.

    Cohere: poseban response parser (_extract_cohere)
    Svi ostali: _extract_openai_compat
    """
    await asyncio.sleep(random.uniform(0.3, 1.5))

    if prov_upper == "GEMINI":
        return await _call_gemini_with_full_rotation(
            self, sys_content, user_prompt, opt_temp, max_tokens,
            preferred_model=model,
        )

    if prov_upper == "GEMMA":
        return await _call_gemma_with_rotation(
            self, sys_content, user_prompt, opt_temp, max_tokens,
            preferred_model=model,
        )

    key = self.fleet.get_best_key(prov_upper)
    if not key:
        return None, None

    from network.provider_urls import get_url
    url = get_url(prov_upper)

    messages = _build_messages(sys_content, user_prompt, model)
    payload = {
        "model":       model,
        "temperature": opt_temp,
        "max_tokens":  max_tokens,
        "messages":    messages,
    }
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {key}",
    }

    data = await _async_http_post(self, url, headers, payload, prov_upper, prov_upper, key)
    if not data:
        return None, None

    content = _extract_content(prov_upper, data)
    if content:
        return content, f"{prov_upper}-{model}"
    return None, None


# ── Blocking API poziv (za WorkerV2 i ne-async kontekste) ────────────────────
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
    """
    Sinhronizovani (blocking) API poziv za WorkerV2 i slične kontekste.
    Gemini native endpoint se koristi ako je provider GEMINI.
    """
    from network.provider_urls import get_url, get_gemini_url
    from network.rate_limiter import get_key_semaphore, get_provider_semaphore
    import time as _time

    prov_upper = provider.upper()

    # Odaberi URL i payload format ovisno o provajderu
    if prov_upper == "GEMINI":
        url = f"{get_gemini_url(model)}?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = _build_gemini_native_payload(system, user, temperature, max_tokens)
    else:
        url = get_url(prov_upper)
        messages = _build_messages(system, user, model)
        payload = {
            "model":       model,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "messages":    messages,
        }
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    prov_sem = get_provider_semaphore(prov_upper)
    key_sem  = get_key_semaphore(api_key)
    prov_sem.acquire()
    key_sem.acquire()
    try:
        _time.sleep(random.uniform(0.3, 1.2))
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

        if prov_upper == "GEMINI":
            return _extract_gemini_native(data)
        return _extract_content(prov_upper, data)

    finally:
        key_sem.release()
        prov_sem.release()