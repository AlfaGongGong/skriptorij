"""
BooklyFi — network/provider_router_v2.py
V10.5: Model-aware rutiranje s per-provider profilima (avoid_roles, quality_tier).
Nasljednik provider_router.py — backward compatible.
"""

import logging
from typing import Optional, Tuple, List, Dict, Any

from core.model_profiles import PROFILI, ModelProfile, get_profili_za_ulogu

# Per-provider profili — limiti, uloge, kvalitet
try:
    from network.provider_profiles import (
        should_avoid_for_role as _pp_avoid,
        get_quality_tier as _pp_tier,
    )
    _PROFILES_OK = True
except ImportError:
    _PROFILES_OK = False
    def _pp_avoid(provider: str, role: str) -> bool:
        return False
    def _pp_tier(provider: str) -> int:
        return 3

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# SCORING LOGIKA
# ─────────────────────────────────────────────────────────────

# Težine za scoring po dimenzijama (suma = 1.0)
_SCORE_TEZINE = {
    "preferred_role_match": 0.40,   # uloga je u preferred_roles
    "tip_bloka_bonus": 0.15,        # bonus za specifični tip bloka
    "rpm_availability": 0.25,       # relativni rpm (viši = bolje)
    "blacklist_penalty": -1.0,      # diskvalifikacija ako je blacklisted
}

# Bonus za model-tip_bloka kombinacije empirijski određene
_TIP_BLOKA_BONUSI: Dict[str, Dict[str, float]] = {
    "dijalog": {
        "gemini_3_flash": 0.12,        # FIX: bili set elementi bez vrijednosti
        "gemini_31_flash_lite": 0.12,
        "gemini_25_flash_lite": 0.12,
        "gemma4_26b": 0.10,
        "gemma4_31b": 0.10,
        "gemini_25_flash": 0.15,
        "gemini_20_flash": 0.10,
        "mistral_large": 0.05,
    },
    "poetski": {
        "gemini_25_flash": 0.20,
        "gemini_20_flash": 0.15,
    },
    "naracija": {
        "gemini_25_flash": 0.10,
        "gemini_20_flash": 0.08,
        "command_r_plus_cohere": 0.05,
    },
    "tehnicki": {
        "mistral_large": 0.15,
        "deepseek_openrouter": 0.10,
        "qwen_chutes": 0.05,
    },
    "dark_fantasy": {
        "gemini_25_flash": 0.20,
        "gemini_20_flash": 0.12,
        "gemini_3_flash": 0.10,
    },
    "horror_akcija": {
        "gemini_25_flash": 0.18,
        "gemini_20_flash": 0.10,
    },
    "horror_atmosfera": {
        "gemini_25_flash": 0.20,
        "gemini_3_flash": 0.10,
        "gemini_20_flash": 0.12,
    },
}

# Maximalni rpm u fleeti (za normalizaciju)
_MAX_RPM = 30


def _score_model(
    profil: ModelProfile,
    uloga: str,
    tip_bloka: Optional[str] = None,
) -> float:
    """
    Izračunava suitability score za model na osnovu uloge i tipa bloka.
    Vraća float 0.0–1.0+. Blacklisted ili avoid modeli vraćaju -1.0.

    V10.5: Integrira per-provider avoid_roles i quality_tier iz provider_profiles.
    """
    # Diskvalifikacija iz ModelProfile blackliste
    if uloga in profil.blacklisted_roles:
        return -1.0

    # Diskvalifikacija iz ProviderProfile avoid_roles
    # (npr. GROQ ne za SCORER, GITHUB ne za PREVODILAC, MISTRAL ne za bulk)
    if _PROFILES_OK and _pp_avoid(profil.provider, uloga):
        return -1.0

    score = 0.0

    # Preferred role match
    if uloga in profil.preferred_roles:
        score += _SCORE_TEZINE["preferred_role_match"]

    # Tip bloka bonus
    if tip_bloka and tip_bloka in _TIP_BLOKA_BONUSI:
        score += _TIP_BLOKA_BONUSI[tip_bloka].get(profil.ime, 0.0)

    # RPM availability (normalizirano)
    rpm_score = min(profil.rpm_limit / _MAX_RPM, 1.0) if profil.rpm_limit > 0 else 0.0
    score += rpm_score * _SCORE_TEZINE["rpm_availability"]

    # Quality tier bonus iz provider_profiles (tier 1 = +0.10, tier 4 = 0)
    # Osigurava da tier-1 provajderi (Gemini, GitHub) dobiju prednost
    if _PROFILES_OK:
        tier = _pp_tier(profil.provider)
        tier_bonus = max(0.0, (4 - tier) * 0.04)  # tier1=+0.12, tier2=+0.08, tier3=+0.04, tier4=0
        score += tier_bonus

    return score


# ─────────────────────────────────────────────────────────────
# GLAVNI ROUTER
# ─────────────────────────────────────────────────────────────

class ProviderRouterV2:
    """
    Model-aware router koji bira optimalni model za svaki zadatak.
    Koristi ModelProfile scoring + dostupnost API ključeva.
    """

    def __init__(self, dostupni_kljucevi: Optional[Dict[str, List[str]]] = None):
        self.dostupni_kljucevi = dostupni_kljucevi or {}
        self._health_scores: Dict[str, float] = {}

    def set_health_score(self, provider: str, score: float) -> None:
        self._health_scores[provider] = max(0.0, min(1.0, score))

    def get_health_score(self, provider: str) -> float:
        return self._health_scores.get(provider, 1.0)

    def _provider_dostupan(self, profil: ModelProfile) -> bool:
        if not self.dostupni_kljucevi:
            return True
        kljucevi = self.dostupni_kljucevi.get(profil.provider, [])
        return len(kljucevi) > 0

    def _get_kljuc(self, provider: str) -> Optional[str]:
        kljucevi = self.dostupni_kljucevi.get(provider, [])
        return kljucevi[0] if kljucevi else None

    def get_best_model(
        self,
        uloga: str,
        tip_bloka: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """
        Vraća (provider, api_model_string, api_key) za optimalni model.
        """
        exclude = exclude or []
        kandidati = []

        for ime, profil in PROFILI.items():
            if ime in exclude:
                continue
            if not self._provider_dostupan(profil):
                continue

            score = _score_model(profil, uloga, tip_bloka)
            if score < 0:
                continue

            health = self.get_health_score(profil.provider)
            if health < 0.1:
                logger.warning(f"Provider {profil.provider} health={health:.2f} — preskačem")
                continue

            final_score = score * health
            kandidati.append((final_score, ime, profil))

        if not kandidati:
            logger.error(f"Nema dostupnih modela za ulogu={uloga}, tip_bloka={tip_bloka}")
            return None

        kandidati.sort(key=lambda x: x[0], reverse=True)
        best_score, best_ime, best_profil = kandidati[0]

        api_key = self._get_kljuc(best_profil.provider)
        logger.info(
            f"RouterV2: uloga={uloga} tip={tip_bloka} → "
            f"{best_ime} ({best_profil.provider}) score={best_score:.3f}"
        )
        return best_profil.provider, best_profil.api_model_string, api_key

    def get_ranked_models(
        self,
        uloga: str,
        tip_bloka: Optional[str] = None,
    ) -> List[Tuple[float, str, ModelProfile]]:
        result = []
        for ime, profil in PROFILI.items():
            if not self._provider_dostupan(profil):
                continue
            score = _score_model(profil, uloga, tip_bloka)
            if score < 0:
                continue
            health = self.get_health_score(profil.provider)
            result.append((score * health, ime, profil))
        result.sort(key=lambda x: x[0], reverse=True)
        return result

    def log_ranking(self, uloga: str, tip_bloka: Optional[str] = None) -> None:
        ranking = self.get_ranked_models(uloga, tip_bloka)
        logger.debug(f"=== Ranking: uloga={uloga} tip={tip_bloka} ===")
        for score, ime, profil in ranking:
            logger.debug(f"  {score:.3f}  {ime:30s}  {profil.provider}")


# Singleton instanca
provider_router_v2 = ProviderRouterV2()


def init_router_v2(dostupni_kljucevi: Dict[str, List[str]]) -> None:
    """Inicijalizira router s dostupnim ključevima. Poziva se iz app.py pri startu."""
    global provider_router_v2
    provider_router_v2 = ProviderRouterV2(dostupni_kljucevi)
    logger.info(f"RouterV2 inicijaliziran. Provideri: {list(dostupni_kljucevi.keys())}")


if __name__ == "__main__":
    router = ProviderRouterV2()
    print("=== Test: prevodilac / dijalog ===")
    result = router.get_best_model("prevodilac", "dijalog")
    print(f"Rezultat: {result}")
    print()
    print("=== Test: validator ===")
    result2 = router.get_best_model("validator")
    print(f"Rezultat: {result2}")
    print()
    print("=== Ranking: prevodilac / poetski ===")
    for score, ime, profil in router.get_ranked_models("prevodilac", "poetski"):
        print(f"  {score:.3f}  {ime}")
