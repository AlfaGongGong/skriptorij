# network/provider_urls.py
# ISPRAVKE:
#   BUG#3 FIX: COHERE URL ažuriran s v1/chat na v2/chat
#   ENDPOINT FIX (v10.7): GEMINI prebačen na native endpoint.
#     OpenAI-kompatibilni endpoint (/v1beta/openai/) ima free_tier limit=0
#     od maja 2026 — Google ga je ograničio na pay-as-you-go billing.
#     Native endpoint (/v1beta/models/{model}:generateContent) podržava
#     free tier. Model se ugrađuje u URL — get_gemini_url(model) za Gemini.
#   CF-PROXY (v10.8): Gemini preusmjeren kroz Cloudflare Worker.

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
        "GEMMA":       "https://api.together.xyz/v1/chat/completions",
        "OPENROUTER":  "https://openrouter.ai/api/v1/chat/completions",
        "COHERE":      "https://api.cohere.com/v2/chat",
        "GITHUB":      "https://models.inference.ai.azure.com/chat/completions",
        "FIREWORKS":   "https://api.fireworks.ai/inference/v1/chat/completions",
        "CHUTES":      "https://llm.chutes.ai/v1/chat/completions",
        "HUGGINGFACE": "https://router.huggingface.co/v1/chat/completions",
        "KLUSTER":     "https://api.kluster.ai/v1/chat/completions",
    }
    return urls.get(prov.upper(), urls["GROQ"])


# Cloudflare Worker proxy — zaobilazi IP blokade prema Google API-u
GEMINI_BASE_URL = "https://booklyfi.jasenkobozinovic.workers.dev"
GEMINI_DIRECT_BASE_URL = "https://generativelanguage.googleapis.com"  # PATCH3: direktni fallback

def get_gemini_url(model: str) -> str:
    """
    Vraća native Gemini endpoint kroz Cloudflare Worker proxy.
    Primarni URL — Worker zaobilazi IP blokade prema Googleu.
    """
    return f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent"

def get_gemini_direct_url(model: str) -> str:
    """
    PATCH3: Direktni Google API URL (fallback kad Worker vrati 429/pade).
    Bez proxy-ja — može biti blokiran za neke IP-ove ali vrijedi probati.
    """
    return f"{GEMINI_DIRECT_BASE_URL}/v1beta/models/{model}:generateContent"