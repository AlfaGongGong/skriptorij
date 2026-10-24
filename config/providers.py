"""
config/providers.py — jedan izvor istine za provajdere, fallback modele i profile.

MODEL_MAP i AI_MODEL_STRINGS (u ai_config.py) se izvode iz providers.json.
Backward-compatible: svi postojeći pozivaoci rade nepromenjeno.
"""

import json
from pathlib import Path

_PROVIDERS_JSON = Path(__file__).parent / "providers.json"

_PROVIDERS: dict = {}


def _load() -> dict:
    global _PROVIDERS
    if not _PROVIDERS:
        with _PROVIDERS_JSON.open(encoding="utf-8") as f:
            raw = json.load(f)
        _PROVIDERS = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _PROVIDERS


def get_provider(provider: str) -> dict:
    """Vrati dict za provajdera: {"fallback": str, "profiles": dict}"""
    return _load().get(provider.upper(), {})


def get_fallback(provider: str) -> str:
    """Fallback model za provajdera. Prazan string ako nepoznat."""
    return get_provider(provider).get("fallback", "")


def get_profile_model(profile_name: str) -> str | None:
    """API model string za interni profile name (npr. gemini_25_flash → gemini-3.5-flash-lite)."""
    for data in _load().values():
        profiles = data.get("profiles", {})
        if profile_name in profiles:
            return profiles[profile_name]
    return None


def all_fallbacks() -> dict[str, str]:
    """{PROVIDER: fallback_model} — za MODEL_MAP."""
    return {prov: data.get("fallback", "") for prov, data in _load().items()}


def all_profiles() -> dict[str, str]:
    """{profile_name: api_model} — za AI_MODEL_STRINGS."""
    out: dict[str, str] = {}
    for data in _load().values():
        out.update(data.get("profiles", {}))
    return out


def list_providers() -> list[str]:
    return sorted(_load().keys())
