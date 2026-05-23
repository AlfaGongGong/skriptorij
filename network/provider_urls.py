# network/provider_urls.py
# ISPRAVKE:
#   BUG#3 FIX: COHERE URL ažuriran s v1/chat na v2/chat
#   ENDPOINT FIX (v10.7): GEMINI prebačen na native endpoint.
#   Centralne Gemini URL konstante i helperi su u config.ai_config.

from config.ai_config import (
    GEMINI_BASE_URL,
    GEMINI_DIRECT_BASE_URL,
    get_gemini_direct_url,
    get_gemini_url,
)


def get_url(prov):
    urls = {
        # GEMINI: get_url("GEMINI") ne smije biti pozvan direktno — koristi get_gemini_url(model).
        # Ova stavka je fallback-only i namjerno pogrešna da otkrije greške.
        # Svaki kod koji poziva get_url("GEMINI") je bug — treba koristiti _call_gemini_with_full_rotation.
        "GEMINI":      "INVALID_USE_get_gemini_url(model)_NOT_get_url",
        "GROQ":        "https://api.groq.com/openai/v1/chat/completions",
        "CEREBRAS":    "https://api.cerebras.ai/v1/chat/completions",
        "MISTRAL":     "https://api.mistral.ai/v1/chat/completions",
        "SAMBANOVA":   "https://api.sambanova.ai/v1/chat/completions",
        "TOGETHER":    "https://api.together.xyz/v1/chat/completions",
        "GEMMA":       "INVALID_USE_get_gemini_url(model)_NOT_get_url",
        "OPENROUTER":  "https://openrouter.ai/api/v1/chat/completions",
        "COHERE":      "https://api.cohere.com/v2/chat",
        "GITHUB":      "https://models.inference.ai.azure.com/chat/completions",
        "FIREWORKS":   "https://api.fireworks.ai/inference/v1/chat/completions",
        "CHUTES":      "https://llm.chutes.ai/v1/chat/completions",
        "HUGGINGFACE": "https://router.huggingface.co/v1/chat/completions",
        "KLUSTER":     "https://api.kluster.ai/v1/chat/completions",
    }
    return urls.get(prov.upper(), urls["GROQ"])


