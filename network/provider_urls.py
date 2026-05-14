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
        "GEMINI":      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
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

def get_gemini_url(model: str) -> str:
    """
    Vraća native Gemini endpoint s ugrađenim modelom, kroz Cloudflare Worker proxy.
    Native endpoint podržava free tier (za razliku od /v1beta/openai/ koji zahtijeva billing).
    Worker transparentno proslijeđuje zahtjev Googleu sa svoje IP adrese.
    """
    return f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent"