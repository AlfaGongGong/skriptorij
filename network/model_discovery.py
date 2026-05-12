# network/model_discovery.py
#
# Auto-detekcija najjačeg slobodnog modela za svakog AI provajdera.
# Upituje /v1/models endpoint i bira optimalni model prema heuristikama
# (broj parametara, porodica modela, verzija) — bez hardkodiranih naziva.
#
# Strategija:
#   1. Na startu se učitaju FALLBACK_MODELS (konzervativne vrijednosti).
#   2. Pozadinski thread pita svaki provajder za listu modela i osvježava cache.
#   3. Cache ima TTL od 3600s — osvježava se jednom satu u pozadini.
#   4. Ako discovery ne uspije (mrežna greška, timeout, 401) — ostaje fallback.

import re
import time
import logging
import threading
import requests
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600.0  # 1 sat

# ── Endpoints za listanje modela ─────────────────────────────────────────────
# Svi OpenAI-kompatibilni provideri imaju GET /v1/models.
# Gemini koristi isti bearer format ali drugačiji base URL.
# GitHub Models: https://models.inference.ai.azure.com/models (vraća array)
_MODELS_ENDPOINTS: dict[str, str] = {
    "GROQ":        "https://api.groq.com/openai/v1/models",
    "CEREBRAS":    "https://api.cerebras.ai/v1/models",
    "MISTRAL":     "https://api.mistral.ai/v1/models",
    "SAMBANOVA":   "https://api.sambanova.ai/v1/models",
    "TOGETHER":    "https://api.together.xyz/v1/models",
    "OPENROUTER":  "https://openrouter.ai/api/v1/models",
    "FIREWORKS":   "https://api.fireworks.ai/inference/v1/models",
    "KLUSTER":     "https://api.kluster.ai/v1/models",
    "CHUTES":      "https://llm.chutes.ai/v1/models",
    "HUGGINGFACE": "https://router.huggingface.co/v1/models",
    "COHERE":      "https://api.cohere.com/v1/models",
    "GEMINI":      "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "GITHUB":      "https://models.inference.ai.azure.com/models",
}

# ── Fallback modeli (vrijede dok discovery ne uspije) ────────────────────────
FALLBACK_MODELS: dict[str, str] = {
    "CEREBRAS":    "llama-4-scout-17b-16e-instruct",
    "SAMBANOVA":   "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL":     "mistral-small-latest",
    "TOGETHER":    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ":        "llama-3.3-70b-versatile",
    "GEMINI":      "gemini-2.0-flash",
    "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
    "COHERE":      "command-r-plus-08-2024",
    "CHUTES":      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER":     "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS":   "accounts/fireworks/models/llama-v3p3-70b-instruct",
    # BUG-A FIX: GEMMA (gemma-3-27b-it) uklonjen — HTTP 404 od maja 2026.
    # Ako se GEMMA provider ponovo aktivira, ovdje treba staviti validan model.
    # GitHub Models: gpt-4o je jači od gpt-4o-mini i dostupan je na free tier
    "GITHUB":      "gpt-4o",
}

# ── Ključne riječi koje isključuju model iz odabira ──────────────────────────
# Modeli za embeddings, TTS, STT, image gen, guard — nisu chat modeli.
_GLOBAL_EXCLUDE = frozenset([
    "embed", "embedding", "rerank", "reranking",
    "whisper", "tts", "speech", "transcrib",
    "guard", "moderat",
    "imagen", "veo", "lyria", "aqa",
    "vision-only",
    "retrieval", "bert",  # BERT i retrieval modeli nisu generativni
])

# Per-provajder dodatni filteri (lambda prima model_id lowercase)
_PROVIDER_FILTERS: dict[str, list] = {
    "OPENROUTER": [lambda m: m.endswith(":free")],
    "GEMINI":     [
        lambda m: "flash" in m or "gemma-4" in m,
        lambda m: "pro" not in m,
        lambda m: "ultra" not in m,
        lambda m: "embed" not in m,
    ],
    "MISTRAL":    [lambda m: "embed" not in m],
    "COHERE":     [
        lambda m: "embed" not in m,
        lambda m: "rerank" not in m,
        lambda m: "command" in m,
    ],
    "FIREWORKS":  [lambda m: "embedding" not in m],
    "TOGETHER":   [
        lambda m: "embed" not in m,
        lambda m: "rerank" not in m,
        lambda m: "moderat" not in m,
    ],
    "GROQ":       [
        lambda m: "whisper" not in m,
        lambda m: "guard" not in m,
        lambda m: "tts" not in m,
    ],
    # GitHub Models: isključi embeddings i evaluation modele koji nisu chat
    "GITHUB":     [
        lambda m: "embed" not in m,
        lambda m: "text-embedding" not in m,
        lambda m: "evaluation" not in m,
        # GitHub models endpoint ponekad vraća registry URI-je koji nisu
        # direktno pozivi preko /chat/completions i često završavaju s unknown_model.
        lambda m: "azureml://" not in m,
        lambda m: "/registries/" not in m,
        lambda m: "/versions/" not in m,
    ],
}


def _is_valid_chat_model(provider: str, model_id: str) -> bool:
    """Vraća True samo za modele pogodne za chat/completions."""
    m = model_id.lower()

    # Globalni exclude
    if any(kw in m for kw in _GLOBAL_EXCLUDE):
        return False

    # Per-provajder filteri
    for fn in _PROVIDER_FILTERS.get(provider.upper(), []):
        if not fn(m):
            return False

    return True


def _score_model_strength(provider: str, model_id: str) -> float:
    """
    Heuristički score za 'jačinu' modela (veći = bolji).
    Temelji se na broju parametara, porodici modela i verziji.
    """
    m = model_id.lower()
    score = 0.0

    # ── Broj parametara (najvažniji signal) ──────────────────────────────────
    # Traži obrasce kao: 70b, 8b, 3.1b, 405b, 17b-16e itd.
    param_hits = re.findall(r'(\d+(?:\.\d+)?)\s*b\b', m)
    if param_hits:
        max_params = max(float(p) for p in param_hits)
        # Logaritamska skala: 70B ≈ 8.5, 8B ≈ 3.0, 405B ≈ 11.0 (capped)
        score += min(max_params ** 0.6, 18.0)

    # ── Generacija modela ─────────────────────────────────────────────────────
    if "llama-4" in m or "llama4" in m:
        score += 6.0
    elif "llama-3.3" in m:
        score += 4.0
    elif "llama-3.2" in m:
        score += 3.0
    elif "llama-3.1" in m:
        score += 2.5
    elif "llama-3" in m:
        score += 1.5

    if "deepseek-v3" in m or "deepseek-r2" in m:
        score += 6.0
    elif "deepseek-r1" in m:
        score += 5.0
    elif "deepseek" in m:
        score += 2.0

    if "qwen3" in m or "qwen-3" in m:
        score += 5.0
    elif "qwen2.5" in m or "qwen-2.5" in m:
        score += 3.0
    elif "qwen" in m:
        score += 1.0

    if "gemini-3" in m:
        score += 7.0
    elif "gemini-2.5" in m:
        score += 6.0
    elif "gemini-2.0" in m:
        score += 5.0
    elif "gemini-1.5" in m:
        score += 3.0

    if "gemma-4" in m or "gemma4" in m:
        score += 3.5
    elif "gemma-3" in m or "gemma3" in m:
        score += 2.5

    if "mistral-large" in m:
        score += 4.0
    elif "mistral-medium" in m:
        score += 3.0
    elif "mistral-small" in m:
        score += 2.0
    elif "mistral-nemo" in m or "open-mistral-nemo" in m:
        score += 1.5

    if "command-r-plus" in m:
        score += 4.0
    elif "command-r" in m:
        score += 2.5
    elif "command" in m:
        score += 1.0

    # ── OpenAI GPT modeli (GitHub Models, OpenRouter) ─────────────────────────
    # Redosljed je bitan: od specifičnijeg prema opštijem da se izbjegne preklapanje.
    if "gpt-4o" in m and "mini" not in m:
        score += 6.5
    elif "gpt-4o-mini" in m:
        score += 3.5
    elif "gpt-4" in m and "gpt-4o" not in m:
        score += 5.0
    elif "o3-mini" in m:
        score += 3.5
    elif re.search(r'\bo3\b', m):
        score += 6.0
    elif "o1-mini" in m:
        score += 3.0
    elif re.search(r'\bo1\b', m):
        score += 4.5
    elif "gpt-3.5" in m:
        score += 2.0

    # ── Microsoft Phi modeli (GitHub Models) ──────────────────────────────────
    if "phi-4" in m and "mini" not in m:
        score += 4.0
    elif "phi-4-mini" in m:
        score += 2.5
    elif "phi-3.5" in m:
        score += 2.0
    elif "phi-3" in m and "phi-3.5" not in m:
        score += 1.5

    # ── Variante (instruct > turbo > base) ───────────────────────────────────
    if "instruct" in m:
        score += 1.0
    if "turbo" in m:
        score += 0.5
    if "versatile" in m:
        score += 0.5
    if "fast" in m or "lite" in m:
        score -= 0.5  # lite/fast su manje moćni

    # ── Gemini-specifično: flash > flash-lite ─────────────────────────────────
    if provider.upper() == "GEMINI":
        if "flash" in m and "lite" not in m:
            score += 1.5
        elif "flash-lite" in m:
            score += 0.5

    return score


def fetch_models(provider: str, api_key: str, timeout: float = 10.0) -> list[str]:
    """
    Pita provajderov /models endpoint i vraća listu chat-sposobnih model ID-jeva.
    Sortirana je po heurističkom score-u — najjači model je prvi.
    """
    endpoint = _MODELS_ENDPOINTS.get(provider.upper())
    if not endpoint:
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(endpoint, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        logger.warning("[ModelDiscovery] %s GET /models greška: %s", provider, exc)
        return []

    if resp.status_code != 200:
        logger.warning("[ModelDiscovery] %s GET /models → HTTP %d", provider, resp.status_code)
        return []

    try:
        data = resp.json()
    except Exception:
        logger.warning("[ModelDiscovery] %s GET /models — neispravan JSON", provider)
        return []

    # Standardni OpenAI format: {"data": [{"id": "...", ...}]}
    raw_list = []
    if isinstance(data, dict) and "data" in data:
        raw_list = data["data"]
    elif isinstance(data, list):
        raw_list = data

    model_ids: list[str] = []
    for item in raw_list:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("name") or ""
        elif isinstance(item, str):
            mid = item
        else:
            continue
        mid = str(mid).strip()
        if mid and _is_valid_chat_model(provider, mid):
            model_ids.append(mid)

    # Sortiraj: najjači model prvi
    model_ids.sort(key=lambda mid: _score_model_strength(provider, mid), reverse=True)
    logger.debug("[ModelDiscovery] %s: pronađeno %d chat modela", provider, len(model_ids))
    return model_ids


# ── Thread-safe cache ─────────────────────────────────────────────────────────
# _model_cache:      provider_upper → (best_model_id, unix_timestamp)
# _model_list_cache: provider_upper → (sorted_model_ids, unix_timestamp)
# _dead_models:      provider_upper → set of model IDs koji su vratili HTTP 404
#                    Modeli se uklanjaju iz dead seta tek kad ih API ponovo
#                    vrati u listi (tj. provajder ih je vratio u produkciju).
_model_cache: dict[str, tuple[str, float]] = {}
_model_list_cache: dict[str, tuple[list, float]] = {}
_dead_models: dict[str, set] = {}
_cache_lock = threading.Lock()
_dead_lock = threading.Lock()


def mark_model_dead(provider: str, model_id: str) -> None:
    """
    Označava model kao nedostupan (HTTP 404).
    Model ostaje dead sve dok ga API ponovo ne vrati u listi modela
    (tj. dok `_set_cached_model_list` ne registruje oživljavanje).
    """
    prov = provider.upper()
    with _dead_lock:
        if prov not in _dead_models:
            _dead_models[prov] = set()
        _dead_models[prov].add(model_id)
    logger.debug("[ModelDiscovery] %s: model %s označen kao dead (404)", prov, model_id)


def get_dead_models(provider: str) -> frozenset:
    """Vraća skup modela koji su proglašeni nedostupnim (404) za provajdera."""
    prov = provider.upper()
    with _dead_lock:
        return frozenset(_dead_models.get(prov, set()))


def clear_dead_models(provider: str = None) -> None:
    """
    Briše skup dead modela za dati provajder (ili sve provajdere ako provider=None).
    Namijenjena testovima i situacijama kad se želi puna ponovna provjera svih modela.
    """
    with _dead_lock:
        if provider is None:
            _dead_models.clear()
        else:
            _dead_models.pop(provider.upper(), None)


def get_cached_model(provider: str) -> Optional[str]:
    """Vraća cached model ID ako cache nije istekao, inače None."""
    prov = provider.upper()
    with _cache_lock:
        entry = _model_cache.get(prov)
    if entry is None:
        return None
    model_id, ts = entry
    if time.time() - ts > _CACHE_TTL:
        return None
    return model_id


def get_cached_model_list(provider: str) -> list[str]:
    """Vraća punu listu chat modela sortiranu po snazi, ili [] ako cache istekao."""
    prov = provider.upper()
    with _cache_lock:
        entry = _model_list_cache.get(prov)
    if entry is None:
        return []
    model_list, ts = entry
    if time.time() - ts > _CACHE_TTL:
        return []
    return model_list


def _set_cached_model(provider: str, model_id: str) -> None:
    prov = provider.upper()
    with _cache_lock:
        _model_cache[prov] = (model_id, time.time())


def _set_cached_model_list(provider: str, model_list: list[str]) -> None:
    prov = provider.upper()
    now = time.time()
    # Ako API ponovo vrati model koji smo smatrali dead-om, oživimo ga —
    # provajder ga je vratio u produkciju pa je opet validan.
    if model_list:
        with _dead_lock:
            dead = _dead_models.get(prov)
            if dead:
                revived = dead & set(model_list)
                if revived:
                    dead -= revived
                    logger.info("[ModelDiscovery] %s: modeli oživljeni: %s", prov, revived)
    with _cache_lock:
        _model_list_cache[prov] = (model_list, now)
        if model_list:
            _model_cache[prov] = (model_list[0], now)


def select_best_model(provider: str, api_key: str) -> str:
    """
    Vraća ID najjačeg slobodnog modela za dati provajder.
    Redosljed:
      1. Validan cache entry (< 1 sat star)
      2. Live discovery od provajdera
      3. FALLBACK_MODELS (hardkodirana vrijednost)
    """
    prov = provider.upper()

    cached = get_cached_model(prov)
    if cached:
        return cached

    models = fetch_models(prov, api_key)
    if models:
        _set_cached_model_list(prov, models)
        best = models[0]
        logger.info("[ModelDiscovery] %s → %s (auto-odabrano)", prov, best)
        return best

    fallback = FALLBACK_MODELS.get(prov, "")
    if fallback:
        logger.warning("[ModelDiscovery] %s → %s (fallback)", prov, fallback)
    return fallback


def invalidate_cached_model(provider: str, model_id: str) -> Optional[str]:
    """
    Uklanja specifičan model iz cachea (npr. kad vrati HTTP 404).
    Model se ujedno označava kao dead — neće se koristiti iz statičkog
    fallbacka sve dok ga API ponovo ne vrati u listi.
    Promoviše sljedeći model iz liste kao novi best.
    Vraća ID sljedećeg modela, ili None ako nema više dostupnih.
    """
    prov = provider.upper()
    # Označiti kao dead PRIJE nego što dođemo do cachea (bez locka — mark ima vlastiti)
    mark_model_dead(prov, model_id)

    with _cache_lock:
        entry = _model_list_cache.get(prov)
        if entry is None:
            return None
        model_list, ts = entry
        if model_id not in model_list:
            return None
        # Ukloni loš model
        model_list = [m for m in model_list if m != model_id]
        _model_list_cache[prov] = (model_list, ts)
        if model_list:
            _model_cache[prov] = (model_list[0], ts)
            logger.info("[ModelDiscovery] %s: model %s invalidiran → %s", prov, model_id, model_list[0])
            return model_list[0]
        else:
            _model_cache.pop(prov, None)
            logger.warning("[ModelDiscovery] %s: model %s invalidiran — nema više modela u cacheu", prov, model_id)
            return None


# ── Pozadinski refresh ────────────────────────────────────────────────────────

def _refresh_worker(provider_keys: dict[str, str]) -> None:
    """
    Pozadinski thread: osvježava discovery za sve provajdere.
    Pokreće se jednom satu (spava između iteracija).
    """
    while True:
        for prov, key in list(provider_keys.items()):
            if not key:
                continue
            try:
                models = fetch_models(prov, key)
                if models:
                    _set_cached_model_list(prov, models)
                    logger.info("[ModelDiscovery] Refresh: %s → %s", prov, models[0])
            except Exception as exc:
                logger.warning("[ModelDiscovery] Refresh greška %s: %s", prov, exc)
        time.sleep(_CACHE_TTL)


_refresh_thread: Optional[threading.Thread] = None

# Per-provajder lock koji sprječava duplicirane re-discovery threadove.
_rediscover_active: dict[str, bool] = {}
_rediscover_lock = threading.Lock()


def trigger_rediscover_background(provider: str, api_key: str) -> None:
    """
    Pokreće hitan pozadinski re-discovery za dati provajder.
    Koristi se kad su svi modeli iscrpljeni (svi 404'd ili cache prazan)
    da se što prije dobije svježa lista validnih modela.

    Sigurno za višestruko pozivanje — ne pokreće duplikat threadova.
    """
    prov = provider.upper()
    if not api_key:
        return

    with _rediscover_lock:
        if _rediscover_active.get(prov):
            return  # thread već aktivan
        _rediscover_active[prov] = True

    def _worker():
        try:
            logger.info("[ModelDiscovery] Re-discovery %s — tražim svježe modele...", prov)
            models = fetch_models(prov, api_key, timeout=12.0)
            if models:
                _set_cached_model_list(prov, models)
                logger.info("[ModelDiscovery] Re-discovery %s → %s (%d modela)", prov, models[0], len(models))
            else:
                logger.warning("[ModelDiscovery] Re-discovery %s — endpoint nije vratio modele", prov)
        except Exception as exc:
            logger.warning("[ModelDiscovery] Re-discovery %s greška: %s", prov, exc)
        finally:
            with _rediscover_lock:
                _rediscover_active[prov] = False

    t = threading.Thread(target=_worker, name=f"ModelRediscover-{prov}", daemon=True)
    t.start()

def start_background_refresh(fleet_manager) -> None:
    """
    Pokreće pozadinski refresh thread koji svakih sat vremena
    osvježava modele za sve aktivne provajdere.
    Sigurno za višestruko pozivanje — pokreće samo jedan thread.
    """
    global _refresh_thread
    if _refresh_thread is not None and _refresh_thread.is_alive():
        return

    provider_keys: dict[str, str] = {}
    for prov, keys in fleet_manager.fleet.items():
        for ks in keys:
            if ks.available and ks.key:
                provider_keys[prov] = ks.key
                break

    if not provider_keys:
        return

    _refresh_thread = threading.Thread(
        target=_refresh_worker,
        args=(provider_keys,),
        name="ModelDiscoveryRefresh",
        daemon=True,
    )
    _refresh_thread.start()
    logger.info("[ModelDiscovery] Pozadinski refresh thread pokrenut (%d providera)", len(provider_keys))


def prime_cache_sync(fleet_manager) -> None:
    """
    Sinhrono popunjava cache za sve provajdere koji imaju aktivan ključ.
    Pokreće se paralelno (jedan thread po provideru) s kratkim timeoutom.
    Idealno pozvati jednom pri startu, odmah nakon što je fleet učitan.
    """
    provider_keys: dict[str, str] = {}
    for prov, keys in fleet_manager.fleet.items():
        for ks in keys:
            if ks.available and ks.key:
                provider_keys[prov] = ks.key
                break

    threads = []
    for prov, key in provider_keys.items():
        if get_cached_model(prov):
            continue  # već u cacheu

        def _discover(p=prov, k=key):
            try:
                models = fetch_models(p, k, timeout=8.0)
                if models:
                    _set_cached_model_list(p, models)
                    logger.info("[ModelDiscovery] Prime: %s → %s", p, models[0])
            except Exception as exc:
                logger.warning("[ModelDiscovery] Prime greška %s: %s", p, exc)

        t = threading.Thread(target=_discover, name=f"ModelPrime-{prov}", daemon=True)
        threads.append(t)
        t.start()

    # Čekamo max 12 sekundi da svi završe
    for t in threads:
        t.join(timeout=12.0)


# ── Startup provjera ključeva ─────────────────────────────────────────────────

_DAILY_QUOTA_COOLDOWN = 82800  # 23h — isti kao api_fleet._DAILY_QUOTA_RETRY_AFTER


def startup_key_check(fleet_manager) -> None:
    """
    Provjera validnosti SVIH ključeva pri startu servera.
    Za svaki ključ šalje GET /v1/models i ažurira stanje u fleetu:

      HTTP 200      → ključ validan; modeli se cachiraju
      HTTP 401/402/403/412 → ključ nevažeći; označen kao disabled (24h cooldown)
      HTTP 429      → kvota iscrpljena ili rate limit:
                       - body/Retry-After signaliziraju kvotu → dugi cooldown
                       - inače → kratki cooldown (rate limit)
      Greška veze   → stanje se ne mijenja (privremena mrežna greška)

    ANTI-BURST: Ključevi istog provajdera se provjeravaju s razmakom od 1s
    da se izbjegne burst koji uzrokuje 429 pri startu (Google throttluje IP).
    Različiti provajderi rade paralelno (jedan thread po provajderu, ne po ključu).
    """
    # Grupiraj ključeve po provajderu
    by_prov: dict[str, list] = {}
    for prov, keys in fleet_manager.fleet.items():
        prov_u = prov.upper()
        for ks in keys:
            if ks.key and not ks.disabled:
                by_prov.setdefault(prov_u, []).append(ks)

    if not by_prov:
        logger.warning("[KeyCheck] Nema ključeva za provjeru")
        return

    total = sum(len(v) for v in by_prov.values())
    logger.info("[KeyCheck] Provjera %d ključeva (%d provajdera)...", total, len(by_prov))

    def _check_one(prov: str, ks) -> None:
        endpoint = _MODELS_ENDPOINTS.get(prov)
        if not endpoint:
            return

        headers = {
            "Authorization": f"Bearer {ks.key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.get(endpoint, headers=headers, timeout=10.0)
        except requests.exceptions.RequestException as exc:
            logger.warning("[KeyCheck] %s ...%s — mrežna greška: %s", prov, ks.key[-4:], exc)
            return

        status = resp.status_code

        # Parsiramo body samo kad nije 200 (jeftino, kratko)
        body = None
        if status != 200:
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text[:300]}

        # BUG_A FIX: analyze_response se POZIVA SAMO za 401/402/403/412 (nevažeći ključ)
        # i NE za 429 s /models endpointa.
        # Razlog: /v1/models ima odvojene (niže) limite od /v1/chat/completions —
        # 429 na /models ne znači da je completions kvota iscrpljena.
        if status in (401, 402, 403, 412):
            fleet_manager.analyze_response(prov, ks.key, status, resp.headers, body)

        if status == 200:
            logger.info("[KeyCheck] %s ...%s → OK", prov, ks.key[-4:])
            # Bonus: cachiraj modele odmah (ne čekaj prime_cache_sync)
            if not get_cached_model(prov):
                try:
                    data = resp.json()
                    raw_list = data.get("data", data) if isinstance(data, dict) else data
                    model_ids: list[str] = []
                    for item in (raw_list if isinstance(raw_list, list) else []):
                        if isinstance(item, dict):
                            mid = item.get("id") or item.get("name") or ""
                        elif isinstance(item, str):
                            mid = item
                        else:
                            continue
                        mid = str(mid).strip()
                        if mid and _is_valid_chat_model(prov, mid):
                            model_ids.append(mid)
                    if model_ids:
                        model_ids.sort(key=lambda m: _score_model_strength(prov, m), reverse=True)
                        _set_cached_model_list(prov, model_ids)
                        logger.info("[KeyCheck] %s: %d modela cachiran (best: %s)", prov, len(model_ids), model_ids[0])
                except Exception:
                    pass
        elif status in (401, 402, 403, 412):
            logger.warning("[KeyCheck] %s ...%s → NEVAŽEĆI KLJUČ (HTTP %d)", prov, ks.key[-4:], status)
        elif status in (429, 425):
            retry_after_raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after") or ""
            try:
                ra = float(retry_after_raw) if retry_after_raw else 0.0
            except ValueError:
                ra = 0.0
            try:
                from api_fleet import _is_quota_exhausted_body, _is_billing_exhausted_body
                if prov in {"GEMINI", "GEMMA"}:
                    is_quota = ra > 3600 or _is_billing_exhausted_body(body)
                else:
                    is_quota = ra > 3600 or _is_quota_exhausted_body(body)
            except Exception:
                is_quota = ra > 3600
            tip = "KVOTA ISCRPLJENA" if is_quota else "RATE LIMIT"
            logger.warning("[KeyCheck] %s ...%s → %s (HTTP 429)", prov, ks.key[-4:], tip)
        else:
            logger.warning("[KeyCheck] %s ...%s → HTTP %d (ignorišem)", prov, ks.key[-4:], status)

    def _check_provider_keys(prov: str, key_list: list) -> None:
        """
        ANTI-BURST FIX: Provjeri ključeve jednog provajdera sekvencijalno
        s razmakom od 1.2s između ključeva.
        Različiti provajderi rade paralelno (poziva se iz zasebnih threadova).
        """
        for i, ks in enumerate(key_list):
            if i > 0:
                time.sleep(1.2)  # anti-burst: 1.2s između ključeva istog provajdera
            _check_one(prov, ks)

    # Jedan thread po provajderu — unutar svakog threada ključevi su sekvencijalni
    threads = [
        threading.Thread(
            target=_check_provider_keys,
            args=(prov, key_list),
            name=f"KeyCheck-{prov}",
            daemon=True,
        )
        for prov, key_list in by_prov.items()
    ]
    for t in threads:
        t.start()
    # Timeout: max_keys_per_prov * 1.2s * threadova + 10s buffer
    max_keys = max(len(v) for v in by_prov.values())
    timeout = max_keys * 1.5 + 15.0
    for t in threads:
        t.join(timeout=timeout)

    fleet_manager.flush_now()

    all_ks_flat = [(prov, ks) for prov, kl in by_prov.items() for ks in kl]
    valid = sum(1 for _, ks in all_ks_flat if ks.available)
    total_checked = len(all_ks_flat)
    logger.info("[KeyCheck] Gotovo: %d/%d ključeva aktivno", valid, total_checked)
