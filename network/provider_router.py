# network/provider_router.py
# BUGFIX:
#   B21: Debug log "[DEBUG VALIDATOR] provider=..." ostao u produkciji —
#        uklonjen. Taj log se ispisivao za SVAKI AI poziv.

import random
import asyncio
from core.text_utils import _adaptive_temp
from network.http_client import _call_single_provider

PROVIDER_PRIORITY = {
    "PREVODILAC":      ["CEREBRAS", "SAMBANOVA", "GROQ", "TOGETHER", "FIREWORKS", "GEMINI", "MISTRAL", "OPENROUTER"],
    "LEKTOR":          ["GEMINI", "MISTRAL", "CEREBRAS", "GROQ", "COHERE", "TOGETHER", "SAMBANOVA"],
    "KOREKTOR":        ["CEREBRAS", "GROQ", "GEMINI", "MISTRAL", "SAMBANOVA"],
    "VALIDATOR":       ["CEREBRAS", "GROQ", "MISTRAL"],
    "GUARDIAN":        ["GEMINI", "MISTRAL", "CEREBRAS", "COHERE"],
    "POLISH":          ["GEMINI", "MISTRAL", "COHERE", "TOGETHER", "SAMBANOVA"],
    "ANALIZA":         ["CEREBRAS", "GROQ", "MISTRAL", "SAMBANOVA", "GEMINI"],
    "CHAPTER_SUMMARY": ["CEREBRAS", "GROQ", "GEMINI", "MISTRAL"],
    "GLOSAR_UPDATE":   ["GEMINI", "CEREBRAS", "GROQ", "MISTRAL"],
    "SCORER":          ["GEMINI", "MISTRAL", "OPENROUTER"],
}

MODEL_MAP = {
    "CEREBRAS":    "llama-4-scout-17b-16e-instruct",
    "SAMBANOVA":   "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL":     "mistral-small-latest",
    "TOGETHER":    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ":        "llama-3.3-70b-versatile",
    "GEMINI":      "gemma-3-27b-it",
    "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
    "COHERE":      "command-r-plus-08-2024",
    "CHUTES":      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER":     "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS":   "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "GEMMA":       "google/gemma-3-27b-it",
}

TEMP_MAP = {
    "PREVODILAC":      0.32,
    "LEKTOR":          0.45,
    "KOREKTOR":        0.15,
    "VALIDATOR":       0.05,
    "GUARDIAN":        0.10,
    "POLISH":          0.68,
    "ANALIZA":         0.10,
    "CHAPTER_SUMMARY": 0.30,
    "GLOSAR_UPDATE":   0.10,
    "SCORER":          0.05,
}

MAX_TOKENS_MAP = {
    "PREVODILAC":      2800,
    "LEKTOR":          2800,
    "KOREKTOR":        2400,
    "VALIDATOR":       800,
    "GUARDIAN":        2400,
    "POLISH":          2800,
    "ANALIZA":         1024,
    "CHAPTER_SUMMARY": 512,
    "GLOSAR_UPDATE":   512,
    "SCORER":          256,
}


async def _call_ai_engine(
    self, prompt, chunk_idx,
    uloga="LEKTOR", filename="",
    sys_override=None, tip_bloka="naracija"
):
    """
    B21 FIX: Uklonjen debug log koji se ispisivao za svaki AI poziv.
    """
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}
    opt_temp = _adaptive_temp(uloga, tip_bloka, TEMP_MAP.get(uloga, 0.35))
    opt_max_tokens = MAX_TOKENS_MAP.get(uloga, 2400)

    sys_c = sys_override
    if not sys_c:
        if uloga == "LEKTOR":
            sys_c = self._get_lektor_prompt()
        elif uloga == "PREVODILAC":
            sys_c = self._get_prevodilac_prompt()
        elif uloga == "KOREKTOR":
            sys_c = self._get_korektor_prompt()
        elif uloga == "GUARDIAN":
            sys_c = self._get_guardian_prompt()
        elif uloga == "POLISH":
            sys_c = self._get_polish_prompt(tip_bloka)
        elif uloga == "ANALIZA":
            from core.prompts import ANALIZA_SYS
            sys_c = ANALIZA_SYS
        elif uloga == "CHAPTER_SUMMARY":
            from core.prompts import CHAPTER_SUMMARY_SYS
            sys_c = CHAPTER_SUMMARY_SYS
        elif uloga == "GLOSAR_UPDATE":
            from core.prompts import GLOSAR_UPDATE_SYS
            sys_c = GLOSAR_UPDATE_SYS
        elif uloga == "VALIDATOR":
            from core.prompts import GLOSAR_VALIDATION_SYS
            sys_c = GLOSAR_VALIDATION_SYS
        elif uloga == "SCORER":
            from core.prompts import QUALITY_SCORER_SYS
            sys_c = QUALITY_SCORER_SYS

    preferred = PROVIDER_PRIORITY.get(uloga, [])
    ordered = []
    for p in preferred:
        if p in svi_upper:
            ordered.append(p)
    for p in svi_upper:
        if p not in ordered:
            ordered.append(p)

    for attempt in range(3):
        for prov_upper in ordered:
            if self.shared_controls.get("stop"):
                return None, "N/A"

            key = self.fleet.get_best_key(prov_upper)
            if not key:
                continue

            model = MODEL_MAP.get(prov_upper) or self.fleet.get_active_model(prov_upper)
            if not model:
                continue

            await asyncio.sleep(random.uniform(0.2, 0.8))

            raw, label = await _call_single_provider(
                self, prov_upper, model,
                sys_c, prompt,
                opt_temp, max_tokens=opt_max_tokens
            )

            if raw:
                # B21 FIX: uklonjen debug log koji je bio ovdje
                return raw, label

        wait = min(2 ** (attempt + 1), 30) + random.uniform(1, 3)
        self.log(
            f"⚠️ [{uloga}] Pokušaj {attempt+1}/3 neuspješan — čekam {wait:.0f}s...",
            "warning",
        )
        await asyncio.sleep(wait)

    self.log(f"❌ [{uloga}] Svi provideri iscrpljeni za blok {chunk_idx}", "error")
    return None, "N/A"