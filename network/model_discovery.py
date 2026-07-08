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

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600.0

_MODELS_ENDPOINTS: dict[str, str] = {
    "GROQ": "https://api.groq.com/openai/v1/models",
    "CEREBRAS": "https://api.cerebras.ai/v1/models",
    "MISTRAL": "https://api.mistral.ai/v1/models",
    "SAMBANOVA": "https://api.sambanova.ai/v1/models",
    "TOGETHER": "https://api.together.xyz/v1/models",
    "OPENROUTER": "https://openrouter.ai/api/v1/models",
    "FIREWORKS": "https://api.fireworks.ai/inference/v1/models",
    "KLUSTER": "https://api.kluster.ai/v1/models",
    "CHUTES": "https://llm.chutes.ai/v1/models",
    "HUGGINGFACE": "https://router.huggingface.co/v1/models",
    "COHERE": "https://api.cohere.com/v1/models",
    "GEMINI": "https://generativelanguage.googleapis.com/v1beta/models",
    "GITHUB": "https://models.inference.ai.azure.com/models",
}

# FIX 08.07.2026: GROQ i CEREBRAS ažurirani — oba stara fallbacka su mrtva/na izdisaju:
#   • GROQ "llama-3.3-70b-versatile" — Groq je 17.06.2026 najavio deprecation,
#     gašenje 16.08.2026 (izvor: console.groq.com/docs/deprecations). Zamijenjeno
#     zvaničnom preporukom "openai/gpt-oss-120b".
#   • CEREBRAS "llama-4-scout-17b-16e-instruct" — live provjera 31.05.2026 pokazala
#     da Cerebras-ov katalog više NE sadrži ovaj model (svega dva modela ostala:
#     gpt-oss-120b i zai-glm-4.7). Zamijenjeno sa "gpt-oss-120b".
#   Ostali entryji provjereni i ostavljeni: SAMBANOVA (i dalje "battle-tested"
#   po zvaničnoj dokumentaciji), GEMINI (namjerno na 3.1-flash-lite zbog
#   postojećeg timeout fixa, ne dirati bez novog razloga), COHERE (command-r-plus-08-2024
#   potvrđeno dostupan i na free trial ključu). TOGETHER/CHUTES/HUGGINGFACE/KLUSTER/
#   FIREWORKS/GEMMA/GITHUB/OPENROUTER NISU live-provjereni u ovom prolazu — diskaveri
#   mehanizam ispod je pravi safety net za njih, ali vrijedi ih provjeriti ručno
#   (npr. curl na _MODELS_ENDPOINTS ispod) prije nego što se u njih pouzda dugoročno.
FALLBACK_MODELS: dict[str, str] = {
    "CEREBRAS": "gpt-oss-120b",
    "SAMBANOVA": "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL": "mistral-small-latest",
    "TOGETHER": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ": "openai/gpt-oss-120b",
    "GEMINI": "gemini-3.1-flash-lite",  # FIX: 3.5-flash timeoutuje, 3.1-flash-lite je jedini stabilan
    "OPENROUTER": "meta-llama/llama-3.3-70b-instruct:free",
    "COHERE": "command-r-plus-08-2024",
    "CHUTES": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER": "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS": "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "GEMMA": "gemma-4-26b-a4b-it",
    "GITHUB": "gpt-4o",
}

_GLOBAL_EXCLUDE = frozenset(
    [
        "embed",
        "embedding",
        "rerank",
        "reranking",
        "whisper",
        "tts",
        "speech",
        "transcrib",
        "guard",
        "moderat",
        "imagen",
        "veo",
        "lyria",
        "aqa",
        "vision-only",
        "retrieval",
        "bert",
    ]
)

_PROVIDER_FILTERS: dict[str, list] = {
    "OPENROUTER": [lambda m: m.endswith(":free")],
    "GEMINI": [
        lambda m: "flash" in m or "gemma-4" in m,
        lambda m: "pro" not in m,
        lambda m: "ultra" not in m,
        lambda m: "embed" not in m,
    ],
    "MISTRAL": [lambda m: "embed" not in m],
    "COHERE": [
        lambda m: "embed" not in m,
        lambda m: "rerank" not in m,
        lambda m: "command" in m,
    ],
    "FIREWORKS": [lambda m: "embedding" not in m],
    "TOGETHER": [
        lambda m: "embed" not in m,
        lambda m: "rerank" not in m,
        lambda m: "moderat" not in m,
    ],
    "GROQ": [
        lambda m: "whisper" not in m,
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

    param_hits = re.findall(r"(\d+(?:\.\d+)?)\s*b\b", m)
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

    if "gpt-oss-120b" in m:
        score += 6.0
    elif "gpt-oss-20b" in m:
        score += 4.0
    elif "gpt-oss" in m:
        score += 3.0

    if "gpt-4o" in m and "mini" not in m:
        score += 6.5
    elif "gpt-4o-mini" in m:
        score += 3.5
    elif "gpt-4" in m and "gpt-4o" not in m:
        score += 5.0
    elif "o3-mini" in m:
        score += 3.5
    elif re.search(r"\bo3\b", m):
        score += 6.0
    elif "o1-mini" in m:
        score += 3.0
    elif re.search(r"\bo1\b", m):
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


def _fetch_gemini_native_models(api_key: str, timeout: float = 10.0) -> list[str]:
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    model_ids: list[str] = []
    page_token = None

    for _ in range(5):
        url = f"{base_url}?key={api_key}&pageSize=50"
        if page_token:
            url += f"&pageToken={page_token}"

        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            logger.warning("[ModelDiscovery] GEMINI native /models greška: %s", exc)
            break

        if resp.status_code != 200:
            logger.warning(
                "[ModelDiscovery] GEMINI native /models → HTTP %d", resp.status_code
            )
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
            if _is_valid_chat_model("GEMINI", model_id):
                model_ids.append(model_id)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if not model_ids:
        return []

    model_ids.sort(key=lambda m: _score_model_strength("GEMINI", m), reverse=True)
    logger.info(
        "[ModelDiscovery] GEMINI: %d modela (best: %s)", len(model_ids), model_ids[0]
    )
    return model_ids


def fetch_models(provider: str, api_key: str, timeout: float = 10.0) -> list[str]:
    prov = provider.upper()
    endpoint = _MODELS_ENDPOINTS.get(prov)
    if not endpoint:
        return []

    if prov == "GEMINI":
        return _fetch_gemini_native_models(api_key, timeout)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.get(endpoint, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        logger.warning("[ModelDiscovery] %s GET /models greška: %s", provider, exc)
        return []

    if resp.status_code != 200:
        logger.warning(
            "[ModelDiscovery] %s GET /models → HTTP %d", provider, resp.status_code
        )
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    raw_list = (
        data["data"]
        if isinstance(data, dict) and "data" in data
        else (data if isinstance(data, list) else [])
    )

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
    return model_ids


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


def clear_dead_models(provider: str = None) -> None:  # type: ignore
    with _dead_lock:
        if provider is None:
            _dead_models.clear()
        else:
            _dead_models.pop(provider.upper(), None)


def clear_model_list_cache(provider: str = None) -> None:  # type: ignore
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
                    logger.info(
                        "[ModelDiscovery] %s: oživljeni modeli: %s", prov, revived
                    )
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
                logger.info(
                    "[ModelDiscovery] %s: re-discovery završen, %d modela",
                    provider,
                    len(models),
                )
        except Exception as exc:
            logger.warning(
                "[ModelDiscovery] %s: re-discovery greška: %s", provider, exc
            )

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def start_background_discovery(fleet: dict) -> None:
    """Pokretanje periodičnog osvježavanja cache-a za sve provajdere u floti."""

    def _worker():
        while True:
            for provider, key_states in fleet.items():
                if not key_states:
                    continue
                key = (
                    key_states[0].key
                    if hasattr(key_states[0], "key")
                    else str(key_states[0])
                )
                try:
                    models = fetch_models(provider, key)
                    if models:
                        _set_cached_model_list(provider.upper(), models)
                except Exception as exc:
                    logger.debug(
                        "[ModelDiscovery] %s: discovery greška: %s", provider, exc
                    )
            time.sleep(_CACHE_TTL)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
