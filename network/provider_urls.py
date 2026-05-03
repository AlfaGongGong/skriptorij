# network/provider_urls.py
# ISPRAVKE:
#   BUG#3 FIX: COHERE URL ažuriran s v1/chat na v2/chat
#              Cohere je zamijenio v1 API — v1/chat ne vraća choices[] odgovor
#              Ispravan endpoint: https://api.cohere.com/v2/chat

def get_url(prov):
    urls = {
        "GEMINI":      "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GROQ":        "https://api.groq.com/openai/v1/chat/completions",
        "CEREBRAS":    "https://api.cerebras.ai/v1/chat/completions",
        "MISTRAL":     "https://api.mistral.ai/v1/chat/completions",
        "SAMBANOVA":   "https://api.sambanova.ai/v1/chat/completions",
        "TOGETHER":    "https://api.together.xyz/v1/chat/completions",
        "GEMMA":       "https://api.together.xyz/v1/chat/completions",
        "OPENROUTER":  "https://openrouter.ai/api/v1/chat/completions",
        # BUG#3 FIX: v1/chat → v2/chat (Cohere deprecated v1 API)
        # Staro: "https://api.cohere.ai/v1/chat"
        "COHERE":      "https://api.cohere.com/v2/chat",
        "GITHUB":      "https://models.inference.ai.azure.com/chat/completions",
        "FIREWORKS":   "https://api.fireworks.ai/inference/v1/chat/completions",
        "CHUTES":      "https://llm.chutes.ai/v1/chat/completions",
        "HUGGINGFACE": "https://router.huggingface.co/v1/chat/completions",
        "KLUSTER":     "https://api.kluster.ai/v1/chat/completions",
    }
    return urls.get(prov.upper(), urls["GROQ"])