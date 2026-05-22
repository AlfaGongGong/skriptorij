# network/provider_router.py
# BUGFIX:
#   B21: Debug log "[DEBUG VALIDATOR] provider=..." ostao u produkciji —
#        uklonjen. Taj log se ispisivao za SVAKI AI poziv.

import random
import asyncio
from core.text_utils import _adaptive_temp
from network.http_client import _call_single_provider, ContentFilterError

PROVIDER_PRIORITY = {
    "PREVODILAC":      ["CEREBRAS", "SAMBANOVA", "GROQ", "TOGETHER", "FIREWORKS", "GEMINI", "MISTRAL", "OPENROUTER", "GITHUB"],
    "LEKTOR":          ["GEMINI", "MISTRAL", "CEREBRAS", "GROQ", "COHERE", "TOGETHER", "SAMBANOVA", "GITHUB"],
    "KOREKTOR":        ["CEREBRAS", "GROQ", "GEMINI", "MISTRAL", "SAMBANOVA", "GITHUB"],
    "VALIDATOR":       ["CEREBRAS", "GROQ", "MISTRAL", "GITHUB"],
    "GUARDIAN":        ["GEMINI", "MISTRAL", "CEREBRAS", "COHERE", "GITHUB"],
    "POLISH":          ["GEMINI", "MISTRAL", "COHERE", "TOGETHER", "SAMBANOVA", "GITHUB"],
    "ANALIZA":         ["CEREBRAS", "GROQ", "MISTRAL", "SAMBANOVA", "GEMINI", "GITHUB"],
    "CHAPTER_SUMMARY": ["CEREBRAS", "GROQ", "GEMINI", "MISTRAL", "GITHUB"],
    "GLOSAR_UPDATE":   ["GEMINI", "CEREBRAS", "GROQ", "MISTRAL", "GITHUB"],
    "SCORER":          ["GEMINI", "MISTRAL", "OPENROUTER", "GITHUB"],
}

MODEL_MAP = {
    "CEREBRAS":    "llama-4-scout-17b-16e-instruct",
    "SAMBANOVA":   "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL":     "mistral-small-latest",
    "TOGETHER":    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ":        "llama-3.3-70b-versatile",
    "GEMINI":      "gemini-2.0-flash",          # FIX: gemma-3-27b-it ugašen (404)
    "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
    "COHERE":      "command-r-plus-08-2024",
    "CHUTES":      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER":     "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS":   "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "GEMMA":       None,                 # DEAD: 404 na Gemini API od maja 2026 — preskači
    "GITHUB":      "gpt-4o",                    # GitHub Models: jak backup kad Gemini presuši
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

_MODEL_TUNING_BY_ID = {
    "gemini-2.0-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR": {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
    },
    "gemma-3-27b-it": {
        "PREVODILAC": {"temp_mul": 0.82, "max_tokens": 1800},
        "LEKTOR": {"temp_mul": 0.85, "max_tokens": 1800},
        "VALIDATOR": {"temp_mul": 0.70, "max_tokens": 600},
        "KOREKTOR": {"temp_mul": 0.95, "max_tokens": 1400},
    },
    "mistral-small-latest": {
        "PREVODILAC": {"temp_mul": 0.92, "max_tokens": 2400},
        "LEKTOR": {"temp_mul": 0.95, "max_tokens": 2400},
        "VALIDATOR": {"temp_mul": 0.85, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 2000},
    },
    "command-r-plus-08-2024": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2200},
        "LEKTOR": {"temp_mul": 0.92, "max_tokens": 2200},
        "VALIDATOR": {"temp_mul": 0.80, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
    },
    "gpt-4o": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2400},
        "LEKTOR": {"temp_mul": 0.93, "max_tokens": 2400},
        "VALIDATOR": {"temp_mul": 0.80, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
    },
}

_MODEL_FAMILY_TUNING = {
    "gemini-": {"temp_mul": 0.90, "max_tokens": 2200},
    "gemma-": {"temp_mul": 0.84, "max_tokens": 1800},
    "mistral": {"temp_mul": 0.95, "max_tokens": 2400},
    "command-r": {"temp_mul": 0.92, "max_tokens": 2200},
    "gpt-4": {"temp_mul": 0.93, "max_tokens": 2400},
    "llama": {"temp_mul": 0.98, "max_tokens": 2600},
    "deepseek": {"temp_mul": 0.95, "max_tokens": 2300},
}


def _resolve_model_generation_params(uloga: str, model: str, base_temp: float, base_max_tokens: int) -> tuple[float, int]:
    """
    Model-specifični tuning preko:
      1) tačnog model ID override-a
      2) fallback family heuristike
    """
    role = (uloga or "").upper()
    model_l = (model or "").lower()

    temp = float(base_temp)
    max_tokens = int(base_max_tokens)

    exact = _MODEL_TUNING_BY_ID.get(model_l, {}).get(role)
    if exact:
        temp *= float(exact.get("temp_mul", 1.0))
        max_tokens = min(max_tokens, int(exact.get("max_tokens", max_tokens)))
    else:
        for family, cfg in _MODEL_FAMILY_TUNING.items():
            if family in model_l:
                temp *= float(cfg.get("temp_mul", 1.0))
                max_tokens = min(max_tokens, int(cfg.get("max_tokens", max_tokens)))
                break

    temp = max(0.0, min(temp, 1.0))
    max_tokens = max(128, max_tokens)
    return temp, max_tokens


async def _call_ai_engine(
    self, prompt, chunk_idx,
    uloga="LEKTOR", filename="",
    sys_override=None, tip_bloka="naracija"
):
    """
    B21 FIX: Uklonjen debug log koji se ispisivao za svaki AI poziv.
    """
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}
    base_temp = _adaptive_temp(uloga, tip_bloka, TEMP_MAP.get(uloga, 0.35))
    base_max_tokens = MAX_TOKENS_MAP.get(uloga, 2400)

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

    for prov_upper in ordered:
        if self.shared_controls.get("stop"):
            return None, "N/A"

        key = self.fleet.get_best_key(prov_upper)
        if not key:
            continue

        model = self.fleet.get_active_model(prov_upper) or MODEL_MAP.get(prov_upper)
        if not model:
            continue

        opt_temp, opt_max_tokens = _resolve_model_generation_params(
            uloga, model, base_temp, base_max_tokens
        )

        await asyncio.sleep(random.uniform(0.2, 0.8))

        try:
            raw, label = await _call_single_provider(
                self, prov_upper, model,
                sys_c, prompt,
                opt_temp, max_tokens=opt_max_tokens
            )
        except ContentFilterError as cfe:
            self.log(f"⛔ [{uloga}] {cfe} — preskačem chunk {chunk_idx}", "warning")
            return None, "CONTENT_FILTER"

        if raw:
            return raw, label

    self.log(f"❌ [{uloga}] Svi provideri iscrpljeni za blok {chunk_idx}", "error")
    return None, "N/A"
