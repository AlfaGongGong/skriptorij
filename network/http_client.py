

# network/http_client.py — V10.3 ISPRAVKA
#
# BUG#4 FIX: Gemma modeli ne podržavaju system role → merge u user poruku
# BUG#5 FIX: _call_gemini_with_full_rotation sada prima i koristi početni model
# OSTALO:    gemini-2.0-flash je na prvom mjestu u GOOGLE_MODEL_POOL (bolji RPD)

import asyncio
import random
import requests
import time

# ── Google model pool — redosljed: gemini-flash prvi (bolji RPD limit) ────────
GOOGLE_MODEL_POOL = [
    {"model": "gemini-2.0-flash",      "rpm": 15, "rpd": 1500},   # primarni
    {"model": "gemma-3-27b-it",        "rpm": 30, "rpd": 14400},  # fallback 1
    {"model": "gemma-3-12b-it",        "rpm": 30, "rpd": 14400},  # fallback 2
    {"model": "gemma-3-4b-it",         "rpm": 30, "rpd": 14400},  # fallback 3
    {"model": "gemini-2.5-flash",      "rpm": 10, "rpd": 500},    # zadnji resort
]

# BUG#4: Modeli koji NE podržavaju system role — konvertujemo u user poruku
_NO_SYSTEM_ROLE = {"gemma-3-27b-it", "gemma-3-12b-it", "gemma-3-4b-it", "gemma-3-1b-it"}

# Per-ključ cache: koji model je trenutno aktivan (index u GOOGLE_MODEL_POOL)
_key_model_cache: dict[str, int] = {}


def _get_model_for_key(key: str) -> str:
    """Inicijalni model za ključ (gemini-2.0-flash za sve — jednako raspoređeno)."""
    if key not in _key_model_cache:
        # Uvijek počni s gemini-2.0-flash (index 0) — ne raspoređuj nasumično
        _key_model_cache[key] = 0
    return GOOGLE_MODEL_POOL[_key_model_cache[key]]["model"]


def _rotate_model_for_key(key: str) -> str | None:
    """Rotira na sljedeći model. Vraća None ako su svi modeli iscrpljeni."""
    start_idx = _key_model_cache.get(key, 0)
    next_idx  = (start_idx + 1) % len(GOOGLE_MODEL_POOL)
    if next_idx == 0:
        # Prošli smo krug
        return None
    _key_model_cache[key] = next_idx
    return GOOGLE_MODEL_POOL[next_idx]["model"]


def _build_messages(sys_content: str | None, user_prompt: str, model: str) -> list:
    """
    BUG#4 FIX: Gradi messages listu ovisno o podršci za system role.
    Gemma modeli ne podržavaju system role → spoji u user poruku.
    """
    if not sys_content:
        return [{"role": "user", "content": user_prompt}]

    if model in _NO_SYSTEM_ROLE:
        # Merge system + user u jednu user poruku
        combined = f"[INSTRUKCIJE]\n{sys_content}\n\n[TEKST ZA OBRADU]\n{user_prompt}"
        return [{"role": "user", "content": combined}]

    return [
        {"role": "system", "content": sys_content},
        {"role": "user",   "content": user_prompt},
    ]


async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key, attempt=1):
    """
    Generički HTTP POST s ispravnim 429 handlingom i retry logicom.
    """
    try:
        resp = await asyncio.to_thread(
            requests.post,
            url,
            headers=headers,
            json=json_payload,
            timeout=(15, 90),
            verify=True,
        )

        try:
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers)
        except Exception:
            pass

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                self.log(f"[{prov_upper}] Neispravan JSON u odgovoru", "error")
                return None

        elif resp.status_code in (429, 425):
            retry_after_raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            try:
                retry_after = float(retry_after_raw) if retry_after_raw else None
            except ValueError:
                retry_after = None

            if retry_after and retry_after > 3600:
                self.log(f"[{prov_upper}] RPD limit (dnevna kvota) — preskačem", "warning")
                return None

            wait = retry_after if retry_after else min(2 ** attempt * 2, 60)
            wait += random.uniform(0.5, 2.0)
            self.log(f"[{prov_upper}] HTTP 429 — čekam {wait:.1f}s (pokušaj {attempt})", "warning")
            await asyncio.sleep(wait)

            if attempt < 3:
                return await _async_http_post(
                    self, url, headers, json_payload, prov, prov_upper, key, attempt + 1
                )
            return None

        elif resp.status_code in (401, 402, 403, 412):
            self.log(f"[{prov_upper}] HTTP {resp.status_code} — ključ nevažeći", "error")
            return None

        elif resp.status_code == 400:
            # Bad request — može biti problem s modelom ili payloadom
            try:
                err_body = resp.json()
                err_msg  = str(err_body)[:200]
            except Exception:
                err_msg = resp.text[:200]
            self.log(f"[{prov_upper}] HTTP 400 Bad Request: {err_msg}", "warning")
            return None

        else:
            self.log(f"[{prov_upper}] HTTP {resp.status_code}", "warning")
            return None

    except requests.exceptions.Timeout:
        self.log(f"[{prov_upper}] Timeout (90s)", "warning")
        return None
    except Exception as e:
        self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:120]}", "error")
        return None


async def _call_single_provider(
    self, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=2400
):
    """
    Poziva jedan provider/model par.
    BUG#5 FIX: za GEMINI prosljeđuje model kao hint (ne ignoriše ga).
    """
    await asyncio.sleep(random.uniform(0.3, 1.5))

    if prov_upper == "GEMINI":
        # BUG#5 FIX: proslijedi model kao preferred_model hint
        return await _call_gemini_with_full_rotation(
            self, sys_content, user_prompt, opt_temp, max_tokens,
            preferred_model=model,
        )

    key = self.fleet.get_best_key(prov_upper)
    if not key:
        return None, None

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {key}",
    }
    from network.provider_urls import get_url
    url = get_url(prov_upper)

    # Provajderi bez system prompt podrške
    if prov_upper in ("GEMMA",) or sys_content is None:
        combined = f"[INSTRUKCIJE]\n{sys_content}\n\n[TEKST]\n{user_prompt}" if sys_content else user_prompt
        messages = [{"role": "user", "content": combined}]
    else:
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user",   "content": user_prompt},
        ]

    payload = {
        "model":       model,
        "temperature": opt_temp,
        "max_tokens":  max_tokens,
        "messages":    messages,
    }

    data = await _async_http_post(self, url, headers, payload, prov_upper, prov_upper, key)
    if not data:
        return None, None

    if "choices" in data and data["choices"]:
        content = data["choices"][0].get("message", {}).get("content", "").strip()
        if content:
            return content, f"{prov_upper}-{model}"
    return None, None


async def _call_gemini_with_full_rotation(
    self, sys_content, user_prompt, opt_temp, max_tokens=2400,
    preferred_model: str = None,
):
    """
    BUG#4 FIX: Gemma modeli dobijaju merged user poruku umjesto system role.
    BUG#5 FIX: Počinje s preferred_model ako je naveden.

    Strategija:
      1. Za svaki dostupni ključ → proba modele počevši od preferred_model
      2. Ako 429 → rotira model za taj ključ
      3. Kad su svi modeli jednog ključa potrošeni → sljedeći ključ
    """
    from network.provider_urls import get_url
    url = get_url("GEMINI")

    keys_list = [ks for ks in self.fleet.fleet.get("GEMINI", []) if ks.available]
    if not keys_list:
        self.log("[GEMINI] Nema dostupnih ključeva", "warning")
        return None, None

    keys_list.sort(key=lambda ks: ks.health_score, reverse=True)

    for ks in keys_list:
        key = ks.key

        # BUG#5 FIX: Ako je preferred_model naveden, počni s njim
        if preferred_model and preferred_model in [m["model"] for m in GOOGLE_MODEL_POOL]:
            # Postavi cache na preferred model
            for i, m in enumerate(GOOGLE_MODEL_POOL):
                if m["model"] == preferred_model:
                    _key_model_cache[key] = i
                    break
            current_model = preferred_model
        else:
            current_model = _get_model_for_key(key)

        tried_models = set()

        for _ in range(len(GOOGLE_MODEL_POOL)):
            if current_model in tried_models:
                break
            tried_models.add(current_model)

            # BUG#4 FIX: Koristi _build_messages koji zna za Gemma ograničenja
            messages = _build_messages(sys_content, user_prompt, current_model)

            payload = {
                "model":       current_model,
                "temperature": opt_temp,
                "max_tokens":  max_tokens,
                "messages":    messages,
            }
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {key}",
            }

            data = await _async_http_post(
                self, url, headers, payload, "GEMINI", "GEMINI", key
            )

            if data and "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content", "").strip()
                if content:
                    return content, f"GEMINI-{current_model}"

            # Rotacija na sljedeći model
            next_model = _rotate_model_for_key(key)
            if next_model is None:
                self.log(f"[GEMINI] Svi modeli iscrpljeni za ključ ...{key[-4:]}", "warning")
                break
            self.log(f"[GEMINI] {current_model} → {next_model}", "warning")
            current_model = next_model
            await asyncio.sleep(0.5)

    self.log("[GEMINI] Svi ključevi i modeli iscrpljeni", "error")
    return None, None



