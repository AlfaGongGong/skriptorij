# network/provider_router.py
# BUGFIX:
#   B21: Debug log "[DEBUG VALIDATOR] provider=..." ostao u produkciji —
#        uklonjen. Taj log se ispisivao za SVAKI AI poziv.

import random
import asyncio
from config.ai_config import MODEL_MAP, PROVIDER_PRIORITY
from core.text_utils import _adaptive_temp
from network.http_client import _call_single_provider, ContentFilterError

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
    "gemini-3.5-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR": {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
        "SCORER":    {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-3.1-flash-lite": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2000},
        "LEKTOR": {"temp_mul": 0.92, "max_tokens": 2000},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 600},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1600},
        "SCORER":    {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.5-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR": {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
        "SCORER":    {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.5-flash-lite": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2000},
        "LEKTOR": {"temp_mul": 0.92, "max_tokens": 2000},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 600},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1600},
        "SCORER":    {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.0-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR": {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR": {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR": {"temp_mul": 1.00, "max_tokens": 1800},
    },
    "gemma-4-26b-it": {
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

    # MAX 2 prolaza kroz listu — drugi prolaz se dešava samo ako su svi bili
    # u kratkom cooldownu (min_gap/RPM). Drugi prolaz čeka najkraći cooldown.
    for attempt in range(2):
        skipped_due_to_cooldown = []

        for prov_upper in ordered:
            if self.shared_controls.get("stop"):
                return None, "N/A"

            # GEMINI i GEMMA upravljaju ključevima interno (_call_gemini/gemma_with_rotation).
            # get_best_key("GEMMA") uvijek vraća None jer GEMMA nema zasebne ključeve u
            # quota_trackeru — koristi GEMINI ključeve. Zato ih ne blokiramo ovdje.
            if prov_upper in ("GEMINI", "GEMMA"):
                # Provjeri ima li GEMINI ključeva uopće (GEMMA koristi iste)
                gemini_keys = self.fleet.fleet.get("GEMINI", [])
                if not gemini_keys:
                    continue
                # Ako su SVI GEMINI ključevi u dugom cooldownu (>60s) — preskači
                from network.quota_tracker import quota_tracker
                has_available_or_short_cd = False
                for ks in gemini_keys:
                    ok, reason = quota_tracker.is_key_available("GEMINI", ks.key)
                    if ok:
                        has_available_or_short_cd = True
                        break
                    import re as _re
                    m = _re.search(r'([\d.]+)s', reason)
                    secs = float(m.group(1)) if m else 99999.0
                    if secs <= 60.0:
                        has_available_or_short_cd = True
                        break
                if not has_available_or_short_cd:
                    skipped_due_to_cooldown.append(prov_upper)
                    continue
            else:
                key = self.fleet.get_best_key(prov_upper)
                if not key:
                    # Provjeri je li razlog kratki cooldown ili nema ključeva uopće
                    keys = self.fleet.fleet.get(prov_upper, [])
                    if keys:
                        skipped_due_to_cooldown.append(prov_upper)
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

        # Svi provajderi preskočeni — ako je razlog kratki cooldown, čekaj i pokušaj ponovo
        if attempt == 0 and skipped_due_to_cooldown:
            # Nađi najkraći preostali cooldown među preskočenim provajderima
            from network.quota_tracker import quota_tracker
            min_wait = 60.0
            for prov_upper in skipped_due_to_cooldown:
                for ks in self.fleet.fleet.get(prov_upper, []):
                    ok, reason = quota_tracker.is_key_available(prov_upper, ks.key)
                    if not ok:
                        import re as _re
                        m = _re.search(r'([\d.]+)s', reason)
                        secs = float(m.group(1)) if m else 60.0
                        if secs < min_wait:
                            min_wait = secs
            wait_s = min(min_wait + 1.0, 30.0)
            self.log(
                f"⏳ [{uloga}] Svi provajderi u kratkom cooldownu — čekam {wait_s:.1f}s (blok {chunk_idx})",
                "warning"
            )
            await asyncio.sleep(wait_s)
            continue  # drugi prolaz
        break

    self.log(f"❌ [{uloga}] Svi provideri iscrpljeni za blok {chunk_idx}", "error")
    return None, "N/A"


# ── V2 routing merge ───────────────────────────────────────────────────────────

"""
BooklyFi — network/provider_router_v2.py
V10.5: Model-aware rutiranje s per-provider profilima (avoid_roles, quality_tier).
Nasljednik provider_router.py — backward compatible.
"""

import logging
from typing import Optional, Tuple, List, Dict

from core.model_profiles import PROFILI, ModelProfile

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
        # Normaliziramo ključeve na uppercase da se izbjegne case mismatch
        # između profil.provider (lowercase) i fleet providera (uppercase).
        self.dostupni_kljucevi = {
            k.upper(): v for k, v in (dostupni_kljucevi or {}).items()
        }
        self._health_scores: Dict[str, float] = {}
        # BUG #6 FIX: round-robin index po provideru da se ne koristi uvijek isti ključ
        self._kljuc_index: Dict[str, int] = {}

    @staticmethod
    def _get_fleet():
        """Lazy pristup globalnoj fleet instanci — izbjegava circular import."""
        try:
            import api_fleet as _af
            return _af._active_fleet
        except (ImportError, AttributeError):
            return None

    def set_health_score(self, provider: str, score: float) -> None:
        self._health_scores[provider.upper()] = max(0.0, min(1.0, score))

    def get_health_score(self, provider: str) -> float:
        prov_u = provider.upper()
        if prov_u in self._health_scores:
            return self._health_scores[prov_u]
        # Izračunaj dinamički iz fleet success_rate — uvijek svježe
        fleet = self._get_fleet()
        if fleet:
            try:
                with fleet.lock:
                    keys = fleet.fleet.get(prov_u, [])
                    rates = [ks.success_rate for ks in keys]
                if rates:
                    return sum(rates) / len(rates)
            except Exception:
                pass
        return 1.0

    def _provider_dostupan(self, profil: ModelProfile) -> bool:
        prov_u = profil.provider.upper()
        # 1. Provjeri lokalni dict (populira ga init_router_v2 ako je pozvan)
        if self.dostupni_kljucevi:
            return len(self.dostupni_kljucevi.get(prov_u, [])) > 0
        # 2. Fallback: pitaj fleet direktno — radi čak i kad init_router_v2 nije pozvan
        fleet = self._get_fleet()
        if fleet:
            return fleet.get_best_key(prov_u) is not None
        return True  # optimistički ako nema flote

    def _get_kljuc(self, provider: str) -> Optional[str]:
        prov_u = provider.upper()
        # 1. Provjeri lokalni dict
        kljucevi = self.dostupni_kljucevi.get(prov_u, [])
        if kljucevi:
            idx = self._kljuc_index.get(prov_u, 0) % len(kljucevi)
            self._kljuc_index[prov_u] = (idx + 1) % len(kljucevi)
            return kljucevi[idx]
        # 2. Fallback: pitaj fleet direktno
        fleet = self._get_fleet()
        if fleet:
            return fleet.get_best_key(prov_u)
        return None

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
    def _mask_result(result):
        if not isinstance(result, tuple) or len(result) < 2:
            return result
        return result[:2]

    router = ProviderRouterV2()
    print("=== Test: prevodilac / dijalog ===")
    result = router.get_best_model("prevodilac", "dijalog")
    print(f"Rezultat: {_mask_result(result)}")
    print()
    print("=== Test: validator ===")
    result2 = router.get_best_model("validator")
    print(f"Rezultat: {_mask_result(result2)}")
    print()
    print("=== Ranking: prevodilac / poetski ===")
    for score, ime, profil in router.get_ranked_models("prevodilac", "poetski"):
        print(f"  {score:.3f}  {ime}")
