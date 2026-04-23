# network/provider_router.py
import random
import asyncio
from core.text_utils import _adaptive_temp
from network.http_client import _call_single_provider

# Prioriteti optimizovani za free tier
PROVIDER_PRIORITY = {
    "PREVODILAC": ["CEREBRAS", "SAMBANOVA", "TOGETHER", "FIREWORKS"],
    "LEKTOR": ["GEMINI", "MISTRAL", "GEMMA"],  # GEMMA kao fallback
    "KOREKTOR": ["CEREBRAS", "GEMINI", "MISTRAL"],
    "VALIDATOR": ["CEREBRAS", "GEMINI"],
    "GUARDIAN": ["GEMINI", "MISTRAL"],
    "POLISH": ["GEMINI", "MISTRAL"],
    "ANALIZA": ["GEMINI", "CEREBRAS"],
    "CHAPTER_SUMMARY": ["CEREBRAS", "GEMINI"],
    "GLOSAR_UPDATE": ["GEMINI", ],
}

# Model mapping
MODEL_MAP = {
    "CEREBRAS": "gpt-oss-20b",
    "SAMBANOVA": "Meta-Llama-3.1-70B-Instruct",
    "MISTRAL": "mistral-small-latest",
    "TOGETHER": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
    "GROQ": "llama-3.1-8b-instant",
    "GEMINI": "gemini-2.0-flash",
    "OPENROUTER": "meta-llama/llama-3.2-3b-instruct:free",
    "COHERE": "command-r-08-2024",
    "CHUTES": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Meta-Llama-3-8B-Instruct",
    "KLUSTER": "klusterai/Meta-Llama-3.1-8B-Instruct-Turbo",
}

async def _call_ai_engine(self, prompt, chunk_idx, uloga="LEKTOR", filename="", sys_override=None, tip_bloka="naracija"):
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}
    opt_max_tokens = 1200  # smanjeno globalno
    pms = []

    # Odabir provajdera prema ulozi
    preferred = PROVIDER_PRIORITY.get(uloga, ["GEMINI", ])
    for up in preferred:
        if up in svi_upper:
            model = MODEL_MAP.get(up, self.fleet.get_active_model(up))
            if model:
                pms.append((up, model))

    if not pms:
        return None, "N/A"

    # Temperatura prema ulozi
    temp_map = {
        "LEKTOR": _adaptive_temp("LEKTOR", tip_bloka, 0.45),
        "PREVODILAC": 0.18,
        "KOREKTOR": 0.22,
        "VALIDATOR": 0.05,
        "GUARDIAN": 0.1,
        "POLISH": _adaptive_temp("POLISH", tip_bloka, 0.70),
        "ANALIZA": 0.1,
        "CHAPTER_SUMMARY": 0.3,
        "GLOSAR_UPDATE": 0.1,
    }
    opt_temp = temp_map.get(uloga, 0.3)

    # System prompt (može biti None za GEMMA)
    sys_c = sys_override
    if uloga == "LEKTOR" and not sys_c:
        sys_c = self._get_lektor_prompt()
    elif uloga == "PREVODILAC" and not sys_c:
        sys_c = self._get_prevodilac_prompt()
    # ... ostale uloge ...

    for attempt in range(3):
        for prov_upper, model in pms:
            # GEMMA ne podržava system prompt
            if prov_upper == "GEMMA":
                combined = f"{sys_c}\n\n{prompt}" if sys_c else prompt
                raw, label = await _call_single_provider(
                    self, prov_upper, model, None, combined, opt_temp, max_tokens=opt_max_tokens
                )
            else:
                raw, label = await _call_single_provider(
                    self, prov_upper, model, sys_c, prompt, opt_temp, max_tokens=opt_max_tokens
                )
            if raw:
                # Za GEMMA, pokušaj parsirati JSON, ako ne uspije, vrati sirovi tekst
                if prov_upper == "GEMMA":
                    from core.text_utils import _smart_extract
                    return _smart_extract(raw), label
                return raw, label
        await asyncio.sleep(2 ** attempt)
    return None, "N/A"