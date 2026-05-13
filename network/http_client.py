

# network/http_client.py — V10.6 ISPRAVKA
#
# BUG#4 FIX: Gemma modeli ne podržavaju system role → merge u user poruku
# BUG#5 FIX: _call_gemini_with_full_rotation sada prima i koristi početni model
# BUG#9 FIX: 429 recursive retry s istim ključem — uklonjen.
#            Sada: kratka pauza → None → caller bira drugi ključ/provider.
# BUG#10 FIX: Per-key semaphore (MAX_CONCURRENT_PER_KEY=1) — uključen.
#             Sprječava višestruke paralelne pozive istim ključem.
# BUG#MODEL FIX (v10.5): _GOOGLE_MODEL_POOL_FALLBACK ažuriran — uklonjeni dead preview modeli.
#             Gemini 429 (RPM) rotira model za isti ključ — svaki model ima nezavisnu
#             RPM/RPD kvotu. Tek kad su svi modeli jednog ključa iscrpljeni → sljedeći ključ.
#             Model rotacija za: 429 (RPM), 404 (mrtav model), timeout, nepoznat model.
# PROXY FIX (v10.6): Gemini requestovi rotiraju kroz external proxy pool da se
#             izbjegne IP-level throttling. Proxy lista se učitava iz dev_api.json
#             ("PROXIES" sekcija) ili iz PROXIES_FILE env varijable.
#             Format: "ip:port:user:pass" po redu. Samo GEMINI koristi proksije —
#             ostali provideri ne throttluju po IP-u.

import asyncio
import random
import requests
from network.rate_limiter import (
    acquire_key,
    release_key,
    register_provider_backoff,
    register_provider_runtime_limits,
)

# ── Proxy pool za Gemini IP rotaciju ─────────────────────────────────────────
# Učitava se lazy pri prvom pozivu. Thread-safe jer je samo čitanje nakon init.
_proxy_pool: list[dict] = []
_proxy_index: int = 0
_proxy_lock = asyncio.Lock() if False else None  # inicijalizira se u _get_next_proxy


def _load_proxy_pool() -> list[dict]:
    """
    Učitava proxy listu iz dev_api.json ("PROXIES": ["ip:port:user:pass", ...])
    ili iz tekstualnog fajla navedenog u PROXIES_FILE env varijabli.
    Format svake stavke: "ip:port:user:pass"
    Vraća listu requests-kompatibilnih proxy dictova.
    """
    import os, json
    from pathlib import Path

    raw_lines: list[str] = []

    # 1. Pokušaj iz dev_api.json
    try:
        cfg_path = Path("dev_api.json")
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text("utf-8"))
            entries = data.get("PROXIES") or data.get("proxies") or []
            if isinstance(entries, list):
                raw_lines = [str(e).strip() for e in entries if e]
    except Exception:
        pass

    # 2. Fallback: tekstualni fajl (PROXIES_FILE env ili Webshare_10_proxies.txt)
    if not raw_lines:
        proxy_file = os.environ.get("PROXIES_FILE", "Webshare_10_proxies.txt")
        try:
            p = Path(proxy_file)
            if p.exists():
                raw_lines = [ln.strip() for ln in p.read_text("utf-8").splitlines() if ln.strip()]
        except Exception:
            pass

    pool = []
    for line in raw_lines:
        parts = line.split(":")
        if len(parts) == 4:
            ip, port, user, pw = parts
            proxy_url = f"http://{user}:{pw}@{ip}:{port}"
            pool.append({"http": proxy_url, "https": proxy_url})
        elif len(parts) == 2:
            # ip:port bez autentifikacije
            ip, port = parts
            proxy_url = f"http://{ip}:{port}"
            pool.append({"http": proxy_url, "https": proxy_url})
    return pool


def _get_next_proxy() -> dict | None:
    """
    Round-robin rotacija kroz proxy pool.
    Thread-safe bez asyncio.Lock (GIL štiti int inkrementaciju u CPython-u).
    Vraća None ako proxy pool nije konfiguriran — request ide direktno.
    """
    global _proxy_pool, _proxy_index
    if not _proxy_pool:
        # Lazy init — učitaj samo jednom
        _proxy_pool = _load_proxy_pool()
    if not _proxy_pool:
        return None
    proxy = _proxy_pool[_proxy_index % len(_proxy_pool)]
    _proxy_index += 1
    return proxy

# ── Google model pool — redosljed: gemini-flash prvi (bolji RPD limit) ────────
# NAPOMENA: gemma-3-27b-it / 12b / 4b ugašeni od maja 2026 (HTTP 404) — uklonjeni.
# BUG#MODEL FIX: gemini-2.5-flash-lite-preview-06-17 i gemini-2.5-flash-preview-05-20
#   vraćaju HTTP 404 od maja 2026 — uklonjeni. Zamijenjeni živim modelima.
# Ovo je statički fallback pool. Dinamički pool se gradi iz model_discovery-a
# kada su dostupni API ključevi (vidi _get_google_model_pool()).
# GEMMA FIX: gemma-4-31b-it dodan u pool — najjači Gemma model (RPM=15, RPD=1500).
#   Koristi iste Gemini API ključeve. _build_messages automatski spaja system+user
#   poruku jer Gemma ne podržava system role (vidi _NO_SYSTEM_ROLE_PATTERNS).
_GOOGLE_MODEL_POOL_FALLBACK = [
    {"model": "gemini-2.0-flash",      "rpm": 15, "rpd": 1500},  # primarni — stabilan, visoki RPD
    {"model": "gemini-2.5-flash",      "rpm": 10, "rpd": 500},   # fallback 1 — noviji, stabilna GA verzija
    {"model": "gemini-2.0-flash-lite", "rpm": 30, "rpd": 1500},  # fallback 2 — visoki RPM, dobar za RPM hitove
    {"model": "gemma-4-31b-it",        "rpm": 15, "rpd": 1500},  # fallback 3 — najjači Gemma, nezavisna kvota
]
# Backward-compatible alias (koristi se direktno u nekim mjestima)
GOOGLE_MODEL_POOL = _GOOGLE_MODEL_POOL_FALLBACK


def _get_google_model_pool() -> list[dict]:
    """
    Vraća pool Gemini modela za rotaciju.
    Ako model_discovery ima svježu listu modela za GEMINI, koristi je
    za određivanje redosljeda unutar statičkog fallback skupa.
    Modeli koji su označeni kao dead (HTTP 404) se filtriraju iz poola.
    Inače vraća statički fallback pool (bez dead modela).
    """
    fallback_by_id = {m["model"]: m for m in _GOOGLE_MODEL_POOL_FALLBACK}

    try:
        from network.model_discovery import get_cached_model_list, get_dead_models
        dead = get_dead_models("GEMINI")
        discovered = get_cached_model_list("GEMINI")
        if discovered:
            # Discovery određuje redosljed unutar whitelistiranog skupa (poznati rpm/rpd).
            # Dead modeli su isključeni.
            pool = [fallback_by_id[mid] for mid in discovered if mid in fallback_by_id and mid not in dead]
            existing_ids = {m["model"] for m in pool}
            for fb in _GOOGLE_MODEL_POOL_FALLBACK:
                if fb["model"] not in existing_ids and fb["model"] not in dead:
                    pool.append(fb)
            if pool:
                return pool
            # Ako su i discovery i fallback prazni (sve dead) — vrati puni fallback
            # kao zadnji resort (bolji od praznog poola koji bi izazvao ZeroDivisionError)
            return _GOOGLE_MODEL_POOL_FALLBACK

        # Nema discovery cache-a — filtriraj dead iz statičkog fallbacka
        if dead:
            filtered = [m for m in _GOOGLE_MODEL_POOL_FALLBACK if m["model"] not in dead]
            return filtered if filtered else _GOOGLE_MODEL_POOL_FALLBACK
    except Exception:
        pass
    return _GOOGLE_MODEL_POOL_FALLBACK

# Modeli koji NE podržavaju system role — konvertujemo u user poruku.
_NO_SYSTEM_ROLE = {"gemma-3-27b-it", "gemma-3-12b-it", "gemma-3-4b-it", "gemma-3-1b-it"}
_NO_SYSTEM_ROLE_PATTERNS = ("gemma-",)

# Per-ključ cache: koji model je trenutno aktivan (index u GOOGLE_MODEL_POOL)
_key_model_cache: dict[str, int] = {}


def _supports_system_role(model: str | None) -> bool:
    if not model:
        return True
    m = model.lower().strip()
    if m in _NO_SYSTEM_ROLE:
        return False
    return not any(pat in m for pat in _NO_SYSTEM_ROLE_PATTERNS)


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

    if not _supports_system_role(model):
        # Merge system + user u jednu user poruku
        combined = f"[INSTRUKCIJE]\n{sys_content}\n\n[TEKST ZA OBRADU]\n{user_prompt}"
        return [{"role": "user", "content": combined}]

    return [
        {"role": "system", "content": sys_content},
        {"role": "user",   "content": user_prompt},
    ]


async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key,
                           _proxy: dict | None = None):
    """
    Generički HTTP POST s ispravnim 429 handlingom.

    BUG#9 FIX: Uklonjen recursive retry s istim ključem na 429.
    BUG#10 FIX: Per-key semaphore osigurava max 1 paralelni poziv po ključu.
    PROXY FIX (v10.6): _proxy parametar omogućava per-request proxy (Gemini).
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
                proxies=_proxy,  # None = direktna veza (svi osim Gemini)
            )
        except requests.exceptions.Timeout:
            self.log(f"[{prov_upper}] Timeout (90s)", "warning")
            try:
                self.fleet.record_network_failure(prov, key)
            except Exception:
                pass
            return None
        except Exception as e:
            self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:120]}", "error")
            try:
                self.fleet.record_network_failure(prov, key)
            except Exception:
                pass
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
                data = resp.json()
                register_provider_runtime_limits(prov_upper, resp.headers, data)
                return data
            except Exception:
                self.log(f"[{prov_upper}] Neispravan JSON u odgovoru", "error")
                return None

        elif resp.status_code in (429, 425):
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
            retry_after_raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            try:
                retry_after = float(retry_after_raw) if retry_after_raw else None
            except ValueError:
                retry_after = None

            # Provider-level backoff da se izbjegne "stampedo" svih ključeva odjednom.
            # BUG_B FIX: provider-level backoff od 60s je previše agresivan — blokira SVE
            # Gemini ključeve odjednom jer _throttle_provider() koristi globalni provider lock.
            # Umjesto toga: koristimo kratki polite-wait samo ako Retry-After nije prisutan.
            # Per-key cooldown (u KeyState) je dovoljan za dulje blokiranje.
            if retry_after and retry_after > 0 and retry_after <= 3600:
                register_provider_backoff(prov_upper, min(retry_after, 15.0))
            elif prov_upper in {"GEMINI", "GEMMA"} and not retry_after:
                # Google često vrati 429 bez Retry-After — kratki backoff da se izbjegne
                # stampedo, ali NE 60s koji bi blokirao sve ključeve istovremeno.
                register_provider_backoff(prov_upper, 5.0)

            if retry_after and retry_after > 3600:
                self.log(f"[{prov_upper}] Kvota iscrpljena (dnevni limit) — biram drugi ključ", "warning")
            else:
                wait = min(retry_after or 3.0, 15.0) + random.uniform(0.3, 1.0)
                self.log(f"[{prov_upper}] HTTP 429 — pauza {wait:.1f}s, biram drugi ključ", "warning")
                await asyncio.sleep(wait)
            return None

        elif resp.status_code in (401, 402, 403, 412):
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
            self.log(f"[{prov_upper}] HTTP {resp.status_code} — ključ nevažeći", "error")
            return None

        elif resp.status_code == 400:
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
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
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
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
            register_provider_runtime_limits(prov_upper, resp.headers, resp_body)
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

    messages = _build_messages(sys_content, user_prompt, model)

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

    # BUG #4 FIX: Snapshot keys under lock — sprječava race condition s analyze_response()
    # koji može mijenjati ks.is_active u drugom asyncio tasku u isto vrijeme.
    with self.fleet.lock:
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
                self, url, headers, payload, "GEMINI", "GEMINI", key,
                _proxy=_get_next_proxy(),  # PROXY FIX: svaki poziv dobiva drugi proxy
            )

            if data and "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content", "").strip()
                if content:
                    return content, f"GEMINI-{current_model}"

            # ── Rotacija modela nakon neuspješnog zahtjeva ────────────────────
            # Svaki Gemini model ima VLASTITE RPM/RPD kvote (gemini-2.0-flash-lite
            # ima 30 RPM, gemini-2.0-flash ima 15 RPM, gemini-2.5-flash ima 10 RPM).
            # BUG FIX: Prethodna verzija je breakala petlju kad is_active=False
            # (billing/dnevna kvota jednog modela). To je POGREŠNO — dnevna kvota
            # gemini-2.0-flash ne znači da su gemini-2.5-flash ili gemma-4 iscrpljeni.
            # Ispravno: nastavi rotaciju kroz sve modele bez break-a.
            # tried_models skup garantuje terminaciju petlje bez duplikata.
            if not ks.is_active:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} — kvota iscrpljena za {current_model} "
                    f"— rotiram na sljedeći model",
                    "warning",
                )
            elif not ks.available:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} u kratkom cooldownu za {current_model} "
                    f"— probam sljedeći model",
                    "warning",
                )

            # 404 / nepoznat model / timeout / 429 → rotiraj model za ovaj ključ
            next_model = _rotate_model_for_key(key)
            if next_model is None:
                self.log(f"[GEMINI] Svi modeli iscrpljeni za ključ ...{key[-4:]}", "warning")
                # Pokušaj hitni re-discovery — možda postoji noviji model koji nije u
                # statičkom fallback poolu, a API ga nudi kao zamjenu za ugašene modele.
                try:
                    from network.model_discovery import trigger_rediscover_background
                    trigger_rediscover_background("GEMINI", key)
                except Exception:
                    pass
                break
            self.log(f"[GEMINI] {current_model} → {next_model}", "warning")
            current_model = next_model
            await asyncio.sleep(0.5)

    # ── Pokušaj s novim ključevima koji su dodani dok je rotacija bila u toku ──
    # keys_list snapshot je uzet na početku poziva. Ako je korisnik dodao novi ključ
    # (ili se neki ključ probudio iz cooldowna) za to vrijeme, nećemo ga vidjeti u
    # starom snapshotu. Jedno svježe čitanje flote ovdje daje im šansu.
    keys_tried = {ks.key for ks in keys_list}
    with self.fleet.lock:
        fresh_keys = [
            ks for ks in self.fleet.fleet.get("GEMINI", [])
            if ks.available and ks.key not in keys_tried
        ]
    if fresh_keys:
        fresh_keys.sort(key=lambda ks: ks.success_rate, reverse=True)
        for ks in fresh_keys:
            key = ks.key
            pool = _get_google_model_pool()
            current_model = _get_model_for_key(key)
            tried_models: set = set()
            for _ in range(len(pool) + 1):
                if current_model in tried_models:
                    break
                tried_models.add(current_model)
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
                    self, url, headers, payload, "GEMINI", "GEMINI", key,
                    _proxy=_get_next_proxy(),
                )
                if data and "choices" in data and data["choices"]:
                    content = data["choices"][0].get("message", {}).get("content", "").strip()
                    if content:
                        return content, f"GEMINI-{current_model}"
                if not ks.is_active:
                    self.log(
                        f"[GEMINI] Ključ ...{key[-4:]} (novi) — kvota iscrpljena za {current_model} "
                        f"— rotiram na sljedeći model",
                        "warning",
                    )
                elif not ks.available:
                    self.log(
                        f"[GEMINI] Ključ ...{key[-4:]} (novi) u kratkom cooldownu za {current_model} "
                        f"— probam sljedeći model",
                        "warning",
                    )
                next_model = _rotate_model_for_key(key)
                if next_model is None:
                    break
                self.log(f"[GEMINI] {current_model} → {next_model}", "warning")
                current_model = next_model
                await asyncio.sleep(0.5)

    self.log("[GEMINI] Svi ključevi i modeli iscrpljeni", "error")
    return None, None
