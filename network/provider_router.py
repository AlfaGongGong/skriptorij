"""network/provider_router.py

AI routing logika. Odabir provajdera i modela prema ulozi, tipu bloka i dostupnosti.
"""

import random
import asyncio
import logging
from typing import Optional, Tuple, List, Dict

from config.ai_config import MODEL_MAP, PROVIDER_PRIORITY
from core.text_utils import _adaptive_temp
from core.model_profiles import PROFILI, ModelProfile
from network.http_client import _call_single_provider, ContentFilterError

try:
    from config.ai_config import (
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

# ── Temperatura i token mape po ulozi ────────────────────────────────────────

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
        "LEKTOR":     {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR":  {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1800},
        "SCORER":     {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-3.1-flash-lite": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2000},
        "LEKTOR":     {"temp_mul": 0.92, "max_tokens": 2000},
        "VALIDATOR":  {"temp_mul": 0.75, "max_tokens": 600},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1600},
        "SCORER":     {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.5-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR":     {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR":  {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1800},
        "SCORER":     {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.5-flash-lite": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2000},
        "LEKTOR":     {"temp_mul": 0.92, "max_tokens": 2000},
        "VALIDATOR":  {"temp_mul": 0.75, "max_tokens": 600},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1600},
        "SCORER":     {"temp_mul": 0.70, "max_tokens": 256},
    },
    "gemini-2.0-flash": {
        "PREVODILAC": {"temp_mul": 0.88, "max_tokens": 2200},
        "LEKTOR":     {"temp_mul": 0.90, "max_tokens": 2200},
        "VALIDATOR":  {"temp_mul": 0.75, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1800},
    },
    "gemma-4-26b-it": {
        "PREVODILAC": {"temp_mul": 0.82, "max_tokens": 1800},
        "LEKTOR":     {"temp_mul": 0.85, "max_tokens": 1800},
        "VALIDATOR":  {"temp_mul": 0.70, "max_tokens": 600},
        "KOREKTOR":   {"temp_mul": 0.95, "max_tokens": 1400},
    },
    "mistral-small-latest": {
        "PREVODILAC": {"temp_mul": 0.92, "max_tokens": 2400},
        "LEKTOR":     {"temp_mul": 0.95, "max_tokens": 2400},
        "VALIDATOR":  {"temp_mul": 0.85, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 2000},
    },
    "command-r-plus-08-2024": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2200},
        "LEKTOR":     {"temp_mul": 0.92, "max_tokens": 2200},
        "VALIDATOR":  {"temp_mul": 0.80, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1800},
    },
    "gpt-4o": {
        "PREVODILAC": {"temp_mul": 0.90, "max_tokens": 2400},
        "LEKTOR":     {"temp_mul": 0.93, "max_tokens": 2400},
        "VALIDATOR":  {"temp_mul": 0.80, "max_tokens": 700},
        "KOREKTOR":   {"temp_mul": 1.00, "max_tokens": 1800},
    },
}

_MODEL_FAMILY_TUNING = {
    "gemini-": {"temp_mul": 0.90, "max_tokens": 2200},
    "gemma-":  {"temp_mul": 0.84, "max_tokens": 1800},
    "mistral":     {"temp_mul": 0.95, "max_tokens": 2400},
    "command-r":   {"temp_mul": 0.92, "max_tokens": 2200},
    "gpt-4":       {"temp_mul": 0.93, "max_tokens": 2400},
    "llama":       {"temp_mul": 0.98, "max_tokens": 2600},
    "deepseek":    {"temp_mul": 0.95, "max_tokens": 2300},
}


def _resolve_model_generation_params(uloga: str, model: str, base_temp: float, base_max_tokens: int) -> tuple[float, int]:
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
    ordered = [p for p in preferred if p in svi_upper]
    for p in svi_upper:
        if p not in ordered:
            ordered.append(p)

    for attempt in range(2):
        skipped_due_to_cooldown = []

        for prov_upper in ordered:
            if self.shared_controls.get("stop"):
                return None, "N/A"

            # GEMINI i GEMMA dijele iste ključeve, ali imaju zasebne cooldown namespace-ove
            # u quota_trackeru — Gemini 429 ne blokira Gemmu automatski.
            if prov_upper in ("GEMINI", "GEMMA"):
                gemini_keys = self.fleet.fleet.get("GEMINI", [])
                if not gemini_keys:
                    continue
                from network.quota_tracker import quota_tracker
                import re as _re
                has_available_or_short_cd = False
                for ks in gemini_keys:
                    if prov_upper == "GEMMA":
                        # Za GEMMA: provjeri GEMINI namespace (zajednički ključ)
                        # pa zatim GEMMA namespace (zaseban cooldown)
                        quota_tracker.is_key_available("GEMINI", ks.key)
                        ok, reason = quota_tracker.is_key_available("GEMMA", ks.key)
                    else:
                        ok, reason = quota_tracker.is_key_available("GEMINI", ks.key)
                    if ok:
                        has_available_or_short_cd = True
                        break
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

        if attempt == 0 and skipped_due_to_cooldown:
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
            continue
        break

    self.log(f"❌ [{uloga}] Svi provideri iscrpljeni za blok {chunk_idx}", "error")
    return None, "N/A"


# ── V2 Routing ────────────────────────────────────────────────────────────────

_SCORE_TEZINE = {
    "preferred_role_match": 0.40,
    "tip_bloka_bonus":      0.15,
    "rpm_availability":     0.25,
    "blacklist_penalty":    -1.0,
}

_TIP_BLOKA_BONUSI: Dict[str, Dict[str, float]] = {
    "dijalog": {
        "gemini_3_flash":       0.12,
        "gemini_31_flash_lite": 0.12,
        "gemini_25_flash_lite": 0.12,
        "gemma4_26b":           0.10,
        "gemma4_31b":           0.10,
        "gemini_25_flash":      0.15,
        "gemini_20_flash":      0.10,
        "mistral_large":        0.05,
    },
    "poetski": {
        "gemini_25_flash": 0.20,
        "gemini_20_flash": 0.15,
    },
    "naracija": {
        "gemini_25_flash":      0.10,
        "gemini_20_flash":      0.08,
        "command_r_plus_cohere": 0.05,
    },
    "tehnicki": {
        "mistral_large":     0.15,
        "deepseek_openrouter": 0.10,
        "qwen_chutes":       0.05,
    },
    "dark_fantasy": {
        "gemini_25_flash": 0.20,
        "gemini_20_flash": 0.15,
    },
}

_MAX_RPM = 30.0


def _score_model(profil: ModelProfile, uloga: str, tip_bloka: Optional[str] = None) -> float:
    if _PROFILES_OK and _pp_avoid(profil.provider, uloga):
        return -1.0

    score = 0.0

    if uloga in profil.preferred_roles:
        score += _SCORE_TEZINE["preferred_role_match"]

    if tip_bloka and tip_bloka in _TIP_BLOKA_BONUSI:
        score += _TIP_BLOKA_BONUSI[tip_bloka].get(profil.ime, 0.0)

    rpm_score = min(profil.rpm_limit / _MAX_RPM, 1.0) if profil.rpm_limit > 0 else 0.0
    score += rpm_score * _SCORE_TEZINE["rpm_availability"]

    if _PROFILES_OK:
        tier = _pp_tier(profil.provider)
        score += max(0.0, (4 - tier) * 0.04)

    return score


class ProviderRouterV2:
    """Model-aware router koji bira optimalni model za svaki zadatak."""

    def __init__(self, dostupni_kljucevi: Optional[Dict[str, List[str]]] = None):
        self.dostupni_kljucevi = {
            k.upper(): v for k, v in (dostupni_kljucevi or {}).items()
        }
        self._health_scores: Dict[str, float] = {}
        self._kljuc_index: Dict[str, int] = {}

    @staticmethod
    def _get_fleet():
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
        if self.dostupni_kljucevi:
            return len(self.dostupni_kljucevi.get(prov_u, [])) > 0
        fleet = self._get_fleet()
        if fleet:
            return fleet.get_best_key(prov_u) is not None
        return True

    def _get_kljuc(self, provider: str) -> Optional[str]:
        prov_u = provider.upper()
        kljucevi = self.dostupni_kljucevi.get(prov_u, [])
        if kljucevi:
            idx = self._kljuc_index.get(prov_u, 0) % len(kljucevi)
            self._kljuc_index[prov_u] = (idx + 1) % len(kljucevi)
            return kljucevi[idx]
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
                logger.warning("Provider %s health=%.2f — preskačem", profil.provider, health)
                continue

            kandidati.append((score * health, ime, profil))

        if not kandidati:
            logger.error("Nema dostupnih modela za ulogu=%s, tip_bloka=%s", uloga, tip_bloka)
            return None

        kandidati.sort(key=lambda x: x[0], reverse=True)
        best_score, best_ime, best_profil = kandidati[0]

        api_key = self._get_kljuc(best_profil.provider)
        logger.info(
            "RouterV2: uloga=%s tip=%s → %s (%s) score=%.3f",
            uloga, tip_bloka, best_ime, best_profil.provider, best_score,
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


provider_router_v2 = ProviderRouterV2()


def init_router_v2(dostupni_kljucevi: Dict[str, List[str]]) -> None:
    global provider_router_v2
    provider_router_v2 = ProviderRouterV2(dostupni_kljucevi)
    logger.info("RouterV2 inicijaliziran. Provideri: %s", list(dostupni_kljucevi.keys()))
