"""network/model_discovery.py

Auto-detekcija chat modela po provajderu.
Strategija:
  1. Na startu vrijede FALLBACK_MODELS (konzervativne vrijednosti).
  2. Pozadinski thread pita svaki provajder za listu modela i osvježava cache.
  3. Cache ima TTL od 3600s — osvježava se jednom na sat u pozadini.
  4. Ako discovery ne uspije — ostaje fallback.
"""

import re
import time
import logging
import threading
import requests
from typing import Optional
from config.ai_config import GEMINI_DIRECT_BASE_URL

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600.0

_MODELS_ENDPOINTS: dict[str, str] = {
    "GROQ":        "https://api.groq.com/openai/v1/models",
    "CEREBRAS":    "https://api.cerebras.ai/v1/models",
    "MISTRAL":     "https://api.mistral.ai/v1/models",
    "SAMBANOVA":   "https://api.sambanova.ai/v1/models",
    "TOGETHER":    "https://api.together.xyz/v1/models",
    "OPENROUTER": "https://openrouter.ai/api/v1/models",
    "FIREWORKS":   "https://api.fireworks.ai/inference/v1/models",
    "KLUSTER":     "https://api.kluster.ai/v1/models",
    "CHUTES":      "https://llm.chutes.ai/v1/models",
    "HUGGINGFACE": "https://router.huggingface.co/v1/models",
    "COHERE":      "https://api.cohere.com/v1/models",
    "GEMINI":      f"{GEMINI_DIRECT_BASE_URL}/v1beta/models",
    "GITHUB":      "https://models.github.ai/catalog/models",
    # FIX 2026-10-20: NVIDIA /v1/models RADI (81 model, test 10:05).
    # Endpoint je bio zakomentarisan zbog pogresne pretpostavke. Vracen.
    "NVIDIA":      "https://integrate.api.nvidia.com/v1/models",
}

FALLBACK_MODELS: dict[str, str] = {
    "CEREBRAS":    "llama-4-scout-17b-16e-instruct",
    "SAMBANOVA":   "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL":     "ministral-14b-latest",
    "TOGETHER":    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ":        "qwen/qwen3.8-27b",
    "GEMINI":      "gemini-3.1-flash-lite",  # i dalje primarni fallback — potvrđeno aktivan (avgust 2026)
    "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
    "COHERE":      "command-r-plus-08-2024",
    "CHUTES":      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER":     "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS":   "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "GEMMA":       "gemma-4-26b-a4b-it",
    "GITHUB":      "openai/gpt-4o",
    "CLOUDFLARE":  "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    # FIX: NVIDIA fallback — potvrđeno na integrate.api.nvidia.com (82 modela, sep 2026)
    "NVIDIA":      "nvidia/nemotron-3-super-120b-a12b",
}

_GLOBAL_EXCLUDE = frozenset([
    # embedding, rerank, retrieval
    "embed", "embedding", "rerank", "reranking", "retrieval", "bert",
    # audio/TTS
    "whisper", "tts", "speech", "transcrib", "orpheus",
    # image/video generation
    "imagen", "veo", "lyria", "aqa", "diffusion", "cosmos",
    # vision (multimodal za slike — ne za prevod teksta)
    "vision-only", "vision-instruct",
    # moderation, guard, safety
    "guard", "moderat",
    # non-HR jezici (arapski, indijski, portugalski, korejski)
    "allam", "jais", "sabia", "sarvam", "sea-lion", "gork",
    # reasoning-only (troši tokene, seče odgovor)
    "o1-", "o3-", "o4-", "-reasoning", "-thinking",
    # reward, protein, special
    "reward", "esmfold", "protein",
])

_PROVIDER_FILTERS: dict[str, list] = {
    "OPENROUTER": [lambda m: m.endswith(":free")],
    "GEMINI": [
        lambda m: "flash" in m,
        lambda m: "pro" not in m,
        lambda m: "ultra" not in m,
        lambda m: "embed" not in m,
    ],
    "MISTRAL":    [
        lambda m: "embed" not in m,
        lambda m: "ministral" not in m,      # mali, 8-14B — preslab
        lambda m: "codestral" not in m,      # code
        lambda m: "pixtral" not in m,        # vision
        lambda m: "devstral" not in m,       # code
        lambda m: "ocr" not in m,            # OCR
        lambda m: "moderation" not in m,     # moderation
        lambda m: "saba" not in m,           # arapski
    ],
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
    "GROQ": [
        lambda m: "whisper" not in m,
        # Reasoning modeli trose tokene na interno razmisljanje i seku odgovor.
        lambda m: "gpt-oss" not in m,
        lambda m: "guard" not in m,
        lambda m: "tts" not in m,
    ],
    "GITHUB": [
        lambda m: "embed" not in m,
        lambda m: "text-embedding" not in m,
        lambda m: "evaluation" not in m,
        lambda m: "azureml://" not in m,
        lambda m: "/registries/" not in m,
        lambda m: "/versions/" not in m,
    ],
    # 2026-10-23: NVIDIA filter
    "NVIDIA": [
        lambda m: "llama2" not in m,
        lambda m: "codellama" not in m,
        lambda m: "-code-" not in m,
        lambda m: "palmyra-creative" not in m,
        lambda m: "reward" not in m,
        lambda m: "guard" not in m,
        lambda m: "cosmos" not in m,
        lambda m: "diffusion" not in m,
    ],
}


def _is_valid_chat_model(provider: str, model_id: str) -> bool:
    m = model_id.lower()
    if any(kw in m for kw in _GLOBAL_EXCLUDE):
        return False
    for fn in _PROVIDER_FILTERS.get(provider.upper(), []):
        if not fn(m):
            return False
    return True


def _score_model_strength(provider: str, model_id: str) -> float:
    m = model_id.lower()
    score = 0.0

    param_hits = re.findall(r'(\d+(?:\.\d+)?)\s*b\b', m)
    if param_hits:
        score += min(max(float(p) for p in param_hits) ** 0.6, 18.0)

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

    # Bonus za non-reasoning modele (ne seku odgovor)
    if "qwen" in m and "thinking" not in m:
        score += 3.0
    if "llama-3.3" in m or "llama-3.1" in m:
        score += 2.5
    # Penal za reasoning modele
    if "gpt-oss" in m or "o1-" in m or "o3-" in m:
        score -= 5.0

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

    if provider.upper() == "GEMINI":
        if "gemini-3.5-flash" in m:
            score += 8.0
        elif "gemini-3.1-flash-lite" in m:
            score += 7.5
        elif "gemini-2.5-flash-lite" in m:
            score += 5.5
        elif "gemini-2.5-flash" in m:
            score += 5.0
        elif "gemini-2.0" in m:
            score -= 20.0
        elif "gemini-1.5" in m:
            score += 1.0
    else:
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

    if "phi-4" in m and "mini" not in m:
        score += 4.0
    elif "phi-4-mini" in m:
        score += 2.5
    elif "phi-3.5" in m:
        score += 2.0
    elif "phi-3" in m and "phi-3.5" not in m:
        score += 1.5

    if "instruct" in m:
        score += 1.0
    if "turbo" in m:
        score += 0.5
    if "versatile" in m:
        score += 0.5
    if "fast" in m or "lite" in m:
        score -= 0.5

    if provider.upper() == "GEMINI":
        if "flash" in m and "lite" not in m:
            score += 1.5
        elif "flash-lite" in m:
            score += 0.5

    return score


def _fetch_gemini_native_models(api_key: str, timeout: float = 10.0,
                                provider_filter: str = "GEMINI") -> list[str]:
    base_url = f"{GEMINI_DIRECT_BASE_URL}/v1beta/models"
    model_ids: list[str] = []
    page_token = None

    for _ in range(5):
        url = f"{base_url}?key={api_key}&pageSize=1000"
        if page_token:
            url += f"&pageToken={page_token}"

        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            logger.warning("[ModelDiscovery] GEMINI native /models greška: %s", exc)
            break

        if resp.status_code != 200:
            logger.warning("[ModelDiscovery] GEMINI native /models → HTTP %d", resp.status_code)
            break

        try:
            data = resp.json()
        except Exception:
            logger.warning("[ModelDiscovery] GEMINI native /models — neispravan JSON")
            break

        for item in data.get("models", []):
            raw_name = item.get("name", "")
            model_id = raw_name.split("/")[-1] if "/" in raw_name else raw_name
            if not model_id:
                continue
            if "generateContent" not in item.get("supportedGenerationMethods", []):
                continue
            # 2026-10-23: filter po provajderu (GEMMA ili GEMINI)
            if provider_filter == "GEMMA":
                if "gemma" in model_id.lower():
                    model_ids.append(model_id)
            elif _is_valid_chat_model("GEMINI", model_id):
                model_ids.append(model_id)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if not model_ids:
        return []

    model_ids.sort(key=lambda m: _score_model_strength(provider_filter, m), reverse=True)
    logger.info("[ModelDiscovery] GEMINI: %d modela (best: %s)", len(model_ids), model_ids[0])
    return model_ids


def _dedup_by_base(models: list[str], provider: str) -> list[str]:
    """
    2026-10-23: Dedup po baznom imenu (mistral-medium-latest = mistral-medium).
    Koristi se za MISTRAL gde API vraca 20+ varijanti iste familije.
    """
    if provider.upper() != "MISTRAL":
        return models
    _BASE_FAMILIES = (
        "mistral-large", "mistral-medium", "mistral-small",
        "mistral-nemo", "open-mistral-nemo",
    )
    seen_bases = set()
    result = []
    for m in models:
        low = m.lower()
        matched = None
        for base in _BASE_FAMILIES:
            if low.startswith(base):
                matched = base
                break
        if matched:
            if matched in seen_bases:
                continue
            seen_bases.add(matched)
        result.append(m)
    return result


def fetch_models(provider: str, api_key: str, timeout: float = 10.0) -> list[str]:
    prov = provider.upper()
    endpoint = _MODELS_ENDPOINTS.get(prov)
    if not endpoint:
        return []

    if prov in ("GEMINI", "GEMMA"):
        # 2026-10-23: GEMMA ide kroz isti Google native /models endpoint
        return _fetch_gemini_native_models(api_key, timeout, provider_filter=prov)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # Cloudflare bot protection za GROQ (error 1010) — isti fingerprint kao http_client
    if prov == "GROQ":
        headers["Accept-Encoding"] = "identity"
        headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Accept-Language"] = "en-US,en;q=0.9"
        headers["Origin"] = "https://console.groq.com"
        headers["Referer"] = "https://console.groq.com/"
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Connection"] = "keep-alive"
        headers["DNT"] = "1"

    try:
        resp = requests.get(endpoint, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        logger.warning("[ModelDiscovery] %s GET /models greška: %s", provider, exc)
        return []

    if resp.status_code != 200:
        _fb = FALLBACK_MODELS.get(prov, "?")
        logger.warning(
            "[ModelDiscovery] %s /models → HTTP %d — koristim fallback: %s",
            provider, resp.status_code, _fb,
        )
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    raw_list = data["data"] if isinstance(data, dict) and "data" in data else (data if isinstance(data, list) else [])

    model_ids = []
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

    model_ids.sort(key=lambda mid: _score_model_strength(provider, mid), reverse=True)
    # 2026-10-23: dedup po baznom imenu (MISTRAL)
    return _dedup_by_base(model_ids, prov)


# ── Thread-safe cache ─────────────────────────────────────────────────────────
_model_cache: dict[str, tuple[str, float]] = {}
_model_list_cache: dict[str, tuple[list, float]] = {}
_dead_models: dict[str, set] = {}
_cache_lock = threading.Lock()
_dead_lock = threading.Lock()


def mark_model_dead(provider: str, model_id: str) -> None:
    prov = provider.upper()
    with _dead_lock:
        _dead_models.setdefault(prov, set()).add(model_id)
    logger.debug("[ModelDiscovery] %s: model %s označen kao dead (404)", prov, model_id)


def get_dead_models(provider: str) -> frozenset:
    prov = provider.upper()
    with _dead_lock:
        return frozenset(_dead_models.get(prov, set()))


def clear_dead_models(provider: str = None) -> None:
    with _dead_lock:
        if provider is None:
            _dead_models.clear()
        else:
            _dead_models.pop(provider.upper(), None)


def clear_model_list_cache(provider: str = None) -> None:
    with _cache_lock:
        if provider is None:
            _model_list_cache.clear()
            _model_cache.clear()
        else:
            prov = provider.upper()
            _model_list_cache.pop(prov, None)
            _model_cache.pop(prov, None)


def get_cached_model(provider: str) -> Optional[str]:
    prov = provider.upper()
    with _cache_lock:
        entry = _model_cache.get(prov)
    if entry is None:
        return None
    model_id, ts = entry
    if time.time() - ts > _CACHE_TTL:
        return None
    return model_id


_MODEL_METRICS_CACHE: dict[str, dict] = {}
"""Cache latencije i RPD-a po modelu. Popunjava se benchmark-om (Faza 2)."""


def enrich_models_with_metrics(provider: str, models: list[str]) -> list[dict]:
    """
    Obogacuje listu modela sa RPD (iz GOOGLE_MODEL_POOL) i latencijom (cache).
    Vraca: [{"model": name, "rpd": int, "latency_s": float}, ...]
    """
    try:
        from config.ai_config import GOOGLE_MODEL_POOL
    except ImportError:
        GOOGLE_MODEL_POOL = []

    out = []
    for m in models:
        rpd = 0
        if provider.upper() == "GEMINI":
            for entry in GOOGLE_MODEL_POOL:
                if entry.get("model") == m:
                    rpd = int(entry.get("rpd", 0))
                    break
        latency = _MODEL_METRICS_CACHE.get(m, {}).get("latency_s", 999.0)
        out.append({"model": m, "rpd": rpd, "latency_s": latency})
    return out


def set_model_latency(model: str, latency_s: float) -> None:
    """Upisi izmerenu latenciju modela u cache (Faza 2)."""
    _MODEL_METRICS_CACHE.setdefault(model, {})["latency_s"] = float(latency_s)


def get_cached_model_list(provider: str) -> list[str]:
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
    if model_list:
        with _dead_lock:
            dead = _dead_models.get(prov)
            if dead:
                revived = dead & set(model_list)
                if revived:
                    logger.info("[ModelDiscovery] %s: oživljeni modeli: %s", prov, revived)
                    _dead_models[prov] = dead - revived
    with _cache_lock:
        _model_list_cache[prov] = (model_list, now)
        if model_list:
            _model_cache[prov] = (model_list[0], now)


def invalidate_cached_model(provider: str, model_id: str) -> None:
    prov = provider.upper()
    mark_model_dead(prov, model_id)
    with _cache_lock:
        entry = _model_list_cache.get(prov)
        if entry is not None:
            lst, ts = entry
            remaining = [m for m in lst if m != model_id]
            _model_list_cache[prov] = (remaining, ts)
            if remaining:
                _model_cache[prov] = (remaining[0], ts)
            else:
                _model_cache.pop(prov, None)


def trigger_rediscover_background(provider: str, key: str) -> None:
    def _run():
        try:
            models = fetch_models(provider, key)
            if models:
                _set_cached_model_list(provider.upper(), models)
                logger.info("[ModelDiscovery] %s: re-discovery završen, %d modela", provider, len(models))
        except Exception as exc:
            logger.warning("[ModelDiscovery] %s: re-discovery greška: %s", provider, exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def start_background_discovery(fleet: dict) -> None:
    """Pokretanje periodičnog osvježavanja cache-a za sve provajdere u floti."""
    def _worker():
        while True:
            for provider, key_states in fleet.items():
                if not key_states:
                    continue
                key = key_states[0].key if hasattr(key_states[0], "key") else str(key_states[0])
                try:
                    models = fetch_models(provider, key)
                    if models:
                        _set_cached_model_list(provider.upper(), models)
                        logger.info(
                            "[ModelDiscovery] %s: %d modela osvjezeno (best=%s)",
                            provider, len(models), models[0],
                        )
                    else:
                        logger.debug(
                            "[ModelDiscovery] %s: 0 modela (koristi FALLBACK: %s)",
                            provider, FALLBACK_MODELS.get(provider.upper(), "?"),
                        )
                except Exception as exc:
                    logger.warning("[ModelDiscovery] %s: discovery greska: %s", provider, exc)
            time.sleep(_CACHE_TTL)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def prime_cache_sync(fleet) -> int:
    """Sinhrono popuni discovery cache pri startu servera.
    Vraca broj popunjenih provajdera.
    """
    filled = 0
    for prov, keys in (fleet or {}).items():
        if not keys:
            continue
        key = keys[0].key if hasattr(keys[0], "key") else str(keys[0])
        try:
            models = fetch_models(prov, key, timeout=5.0)
            if models:
                _set_cached_model_list(prov, models)
                filled += 1
                logger.info("[prime_cache] %s: %d modela", prov, len(models))
        except Exception as exc:
            logger.debug("[prime_cache] %s: %s", prov, exc)
    logger.info("[prime_cache] Popunjeno %d provajdera", filled)
    return filled

