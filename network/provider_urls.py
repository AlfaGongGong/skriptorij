# network/provider_urls.py
def get_url(prov):
    urls = {
        "GEMINI": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GROQ": "https://api.groq.com/openai/v1/chat/completions",
        "CEREBRAS": "https://api.cerebras.ai/v1/chat/completions",
        "MISTRAL": "https://api.mistral.ai/v1/chat/completions",
        "TOGETHER": "https://api.together.xyz/v1/chat/completions",
        "GEMMA": "https://api.together.xyz/v1/chat/completions",
    }
    return urls.get(prov, urls["GROQ"])
