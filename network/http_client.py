

# network/http_client.py — V10.4 ISPRAVKA
#
# BUG#4 FIX: Gemma modeli ne podržavaju system role → merge u user poruku
# BUG#5 FIX: _call_gemini_with_full_rotation sada prima i koristi početni model
# BUG#9 FIX: 429 recursive retry s istim ključem — uklonjen.
#            Sada: kratka pauza → None → caller bira drugi ključ/provider.
# BUG#10 FIX: Per-key semaphore (MAX_CONCURRENT_PER_KEY=1) — uključen.
#             Sprječava višestruke paralelne pozive istim ključem.

import asyncio
import random
import requests
from network.rate_limiter import acquire_key, release_key

# ── Google model pool — redosljed: gemini-flash prvi (bolji RPD limit) ────────
# NAPOMENA: gemma-3-27b-it / 12b / 4b ugašeni od maja 2026 (HTTP 404) — uklonjeni.
# Ovo je statički fallback pool. Dinamički pool se gradi iz model_discovery-a
# kada su dostupni API ključevi (vidi _get_google_model_pool()).
_GOOGLE_MODEL_POOL_FALLBACK = [
    {"model": "gemini-2.0-flash",                    "rpm": 15, "rpd": 1500},  # primarni
    {"model": "gemini-2.5-flash-lite-preview-06-17", "rpm": 10, "rpd": 500},   # fallback 1
    {"model": "gemini-2.5-flash-preview-05-20",      "rpm": 10, "rpd": 500},   # fallback 2 — zadnji resort
]
# Backward-compatible alias (koristi se direktno u nekim mjestima)
GOOGLE_MODEL_POOL = _GOOGLE_MODEL_POOL_FALLBACK


def _get_google_model_pool() -> list[dict]:
    """
    Vraća pool Gemini modela za rotaciju.
    Ako model_discovery ima svježu listu modela za GEMINI, koristi je.
    Inače vraća statički fallback pool.
    Otkriveni modeli idu prvi; statički fallback popunjava ostatak.
    """
    fallback_by_id = {m["model"]: m for m in _GOOGLE_MODEL_POOL_FALLBACK}

    try:
        from network.model_discovery import get_cached_model_list
        discovered = get_cached_model_list("GEMINI")
        if discovered:
            # Runtime whitelist: koristimo samo fallback modele sa provjerenim limitima.
            # Discovery smije odlučiti samo REDOSLJED unutar ovog skupa.
            pool = [fallback_by_id[mid] for mid in discovered if mid in fallback_by_id]
            existing_ids = {m["model"] for m in pool}
            for fb in _GOOGLE_MODEL_POOL_FALLBACK:
                if fb["model"] not in existing_ids:
                    pool.append(fb)
            return pool
    except Exception:
        pass
    return _GOOGLE_MODEL_POOL_FALLBACK

# BUG#4: Modeli koji NE podržavaju system role — konvertujemo u user poruku
_NO_SYSTEM_ROLE = {"gemma-3-27b-it", "gemma-3-12b-it", "gemma-3-4b-it", "gemma-3-1b-it"}

# Per-ključ cache: koji model je trenutno aktivan (index u GOOGLE_MODEL_POOL)
_key_model_cache: dict[str, int] = {}


def _get_model_for_key(key: str) -> str:
    """Inicijalni model za ključ — uvijek počni s prvim modelom u pool-u."""
    pool = _get_google_model_pool()
    if key not in _key_model_cache:
        _key_model_cache[key] = 0
    idx = _key_model_cache[key]
    # Provjeri da index nije van opsega (pool se može promijeniti između poziva)
    if idx >= len(pool):
        _key_model_cache[key] = 0
        idx = 0
    return pool[idx]["model"]


def _rotate_model_for_key(key: str) -> str | None:
    """Rotira na sljedeći model u pool-u. Vraća None ako su svi modeli iscrpljeni."""
    pool = _get_google_model_pool()
    start_idx = _key_model_cache.get(key, 0)
    next_idx  = (start_idx + 1) % len(pool)
    if next_idx == 0:
        # Prošli smo krug
        return None
    _key_model_cache[key] = next_idx
    return pool[next_idx]["model"]


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


async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key):
    """
    Generički HTTP POST s ispravnim 429 handlingom.

    BUG#9 FIX: Uklonjen recursive retry s istim ključem na 429.
      Stari kod: čekaj → ponovi isti ključ do 3× → multiplikacija grešaka.
      Novi kod:  kratka pauza za učtivost → odmah None → caller bira drugi ključ.

    BUG#10 FIX: Per-key semaphore osigurava max 1 paralelni poziv po ključu.

    NOVO: body se parsira i prosljeđuje analyze_response() za bolje
      razlikovanje kvote i rate limita kod 429 grešaka.
    NOVO: Na 404, model se invalidira iz discovery cachea.
    """
    await acquire_key(key, prov_upper)
    try:
        try:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=json_payload,
                timeout=(15, 90),
                verify=True,
            )
        except requests.exceptions.Timeout:
            self.log(f"[{prov_upper}] Timeout (90s)", "warning")
            return None
        except Exception as e:
            self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:120]}", "error")
            return None

        # Parsiramo body za greške (200 ne trebamo parsirati ovdje)
        resp_body = None
        if resp.status_code != 200:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = {"text": resp.text[:300]}

        try:
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers, resp_body)
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

            # analyze_response() je već odredio tip (kvota ili rate limit) i postavio cooldown.
            # Ovdje samo logovati i eventualno čekati kratko za učtivost.
            if retry_after and retry_after > 3600:
                self.log(f"[{prov_upper}] Kvota iscrpljena (dnevni limit) — biram drugi ključ", "warning")
            else:
                wait = min(retry_after or 3.0, 8.0) + random.uniform(0.3, 1.0)
                self.log(f"[{prov_upper}] HTTP 429 — pauza {wait:.1f}s, biram drugi ključ", "warning")
                await asyncio.sleep(wait)
            return None

        elif resp.status_code in (401, 402, 403, 412):
            self.log(f"[{prov_upper}] HTTP {resp.status_code} — ključ nevažeći", "error")
            return None

        elif resp.status_code == 400:
            err_msg = str(resp_body)[:200] if resp_body else resp.text[:200]
            body_l = str(resp_body).lower() if resp_body is not None else resp.text.lower()
            if (
                "unknown_model" in body_l
                or "unknown model" in body_l
                or "nepoznati model" in body_l
            ):
                model_used = (json_payload or {}).get("model", "") if isinstance(json_payload, dict) else ""
                if model_used:
                    try:
                        from network.model_discovery import invalidate_cached_model
                        next_model = invalidate_cached_model(prov_upper, model_used)
                        if next_model:
                            self.log(
                                f"[{prov_upper}] Model {model_used!r} nepoznat (400) → "
                                f"invalidiran, sljedeći: {next_model!r}",
                                "warning",
                            )
                        else:
                            self.log(
                                f"[{prov_upper}] Model {model_used!r} nepoznat (400) — "
                                "nema više modela u cacheu",
                                "warning",
                            )
                    except Exception:
                        pass
            self.log(f"[{prov_upper}] HTTP 400 Bad Request: {err_msg}", "warning")
            return None

        elif resp.status_code == 404:
            # Model ne postoji — ukloni iz discovery cachea i pokušaj sljedeći
            model_used = (json_payload or {}).get("model", "") if isinstance(json_payload, dict) else ""
            if model_used:
                try:
                    from network.model_discovery import invalidate_cached_model
                    next_model = invalidate_cached_model(prov_upper, model_used)
                    if next_model:
                        self.log(
                            f"[{prov_upper}] Model {model_used!r} ne postoji (404) → "
                            f"invalidiran, sljedeći: {next_model!r}",
                            "warning",
                        )
                    else:
                        self.log(
                            f"[{prov_upper}] Model {model_used!r} ne postoji (404) — "
                            "nema više modela u cacheu",
                            "warning",
                        )
                except Exception:
                    self.log(f"[{prov_upper}] HTTP 404 — model ne postoji", "warning")
            else:
                self.log(f"[{prov_upper}] HTTP 404 — resurs nije pronađen", "warning")
            return None

        else:
            self.log(f"[{prov_upper}] HTTP {resp.status_code}", "warning")
            return None

    finally:
        release_key(key)



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
        # Dinamički pool — ne zahtijeva da preferred_model bude u pool-u
        pool = _get_google_model_pool()
        allowed_model_ids = {m["model"] for m in pool}
        if preferred_model and preferred_model in allowed_model_ids:
            current_model = preferred_model
            # Postavi cache index na preferred model ako je u pool-u
            for i, m in enumerate(pool):
                if m["model"] == preferred_model:
                    _key_model_cache[key] = i
                    break
        else:
            current_model = _get_model_for_key(key)

        tried_models = set()

        # +1 u opsegu: preferred_model može biti izvan pool-a (dinamički otkriveni model),
        # pa treba jedan dodatni slot — tried_models skup garantuje bez duplikata.
        for _ in range(len(pool) + 1):
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

