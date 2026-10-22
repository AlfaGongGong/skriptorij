"""
config/model_roles.py — pravila za dinamički izbor modela po ulozi.

Ne hardkodira konkretne modele. Definiše ZAHTEVE koje model mora da ispuni.
Discovery vraća listu, ovaj modul bira.

Primjer:
    enriched = [
        {"model": "gemini-3.5-flash-lite", "rpd": 500, "latency_s": 12.0},
        {"model": "gemini-2.5-flash-lite", "rpd": 20, "latency_s": 6.0},
        {"model": "gemini-3.5-flash",      "rpd": 20, "latency_s": 8.0},
    ]
    pick_model_for_role("PREVODILAC", enriched)  # -> "gemini-3.5-flash-lite" (min_rpd=500)
    pick_model_for_role("SCORER", enriched)      # -> "gemini-2.5-flash-lite" (fast, latency 6s)
"""

from typing import Optional


# Uloga -> zahtevi koje model mora da ispuni
# min_rpd: minimum RPD-a
# prefer_size: "lite" (brži, jeftiniji) ili "full" (kvalitetniji)
# prefer_speed: "fast" (max 15s) ili "any"
# max_latency_s: gornji limit latencije (default 60s)
MODEL_REQUIREMENTS = {
    # Dugi zadaci — treba kapacitet, tolerišemo 12s
    "PREVODILAC": {
        "min_rpd": 500,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 60,
    },
    "LEKTOR": {
        "min_rpd": 500,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 60,
    },
    "KOREKTOR": {
        "min_rpd": 500,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 60,
    },
    "POLISH": {
        "min_rpd": 200,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 60,
    },
    "GUARDIAN": {
        "min_rpd": 200,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 60,
    },
    # Kratki zadaci — hoćemo brzinu, manje RPD-a je OK
    "VALIDATOR": {
        "min_rpd": 100,
        "prefer_size": "lite",
        "prefer_speed": "fast",
        "max_latency_s": 15,
    },
    "SCORER": {
        "min_rpd": 100,
        "prefer_size": "lite",
        "prefer_speed": "fast",
        "max_latency_s": 10,
    },
    "GLOSAR_UPDATE": {
        "min_rpd": 100,
        "prefer_size": "lite",
        "prefer_speed": "fast",
        "max_latency_s": 15,
    },
    "ANALIZA": {
        "min_rpd": 200,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 30,
    },
    "CHAPTER_SUMMARY": {
        "min_rpd": 200,
        "prefer_size": "lite",
        "prefer_speed": "any",
        "max_latency_s": 30,
    },
}

# Default za nepoznate uloge — ne diraj postojeće ponašanje
DEFAULT_REQ = {
    "min_rpd": 0,
    "prefer_size": "lite",
    "prefer_speed": "any",
    "max_latency_s": 999,
}


def pick_model_for_role(role: str, available_models: list[dict]) -> Optional[str]:
    """
    Bira najbolji model za datu ulogu iz liste.

    Args:
        role: "PREVODILAC", "SCORER", "VALIDATOR", itd.
        available_models: [{"model": str, "rpd": int, "latency_s": float}, ...]

    Returns:
        Ime modela ili None ako nema kandidata.
    """
    if not available_models:
        return None

    req = MODEL_REQUIREMENTS.get((role or "").upper(), DEFAULT_REQ)

    candidates = []
    for m in available_models:
        # RPD filter
        if m.get("rpd", 0) < req["min_rpd"]:
            continue
        # Latencija filter
        if m.get("latency_s", 999) > req["max_latency_s"]:
            continue
        # Speed filter
        if req["prefer_speed"] == "fast" and m.get("latency_s", 999) > 15:
            continue
        candidates.append(m)

    if not candidates:
        # Fallback: vrati prvi model (ne diraj postojeće ponašanje)
        return available_models[0].get("model")

    # Rangiraj: prefer_size (lite > full), pa latency
    def rank(m):
        name_lower = m.get("model", "").lower()
        if req["prefer_size"] == "lite":
            size_score = 0 if "lite" in name_lower else 1
        else:
            size_score = 0 if "lite" not in name_lower else 1
        return (size_score, m.get("latency_s", 999))

    candidates.sort(key=rank)
    return candidates[0].get("model")
