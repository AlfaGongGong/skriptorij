# ============================================================================
# SKRIPTORIJ V8 — api_fleet.py
# Fleet Manager: upravljanje API ključevima, health tracking, backoff
# ============================================================================

import json
import os
import random
import time
from pathlib import Path

# Podrazumijevani modeli po provajderu
_DEFAULT_MODELS = {
    "GEMINI": "gemini-2.5-flash",
    "GROQ": "llama-3.3-70b-versatile",
    "CEREBRAS": "llama3.1-8b",
    "SAMBANOVA": "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL": "mistral-large-latest",
    "COHERE": "command-a-03-2025",
    "OPENROUTER": "meta-llama/llama-3.3-70b-instruct",
    "GITHUB": "gpt-4o-mini",
}

# Cooldown nakon rate-limit greške (sekunde)
_COOLDOWN_429 = 60
_COOLDOWN_ERROR = 30


class _KeyState:
    """Interno stanje jednog API ključa."""

    __slots__ = ("key", "cooldown_until", "backoff", "total_requests", "errors")

    def __init__(self, key: str):
        self.key = key
        self.cooldown_until: float = 0.0
        self.backoff: float = 5.0
        self.total_requests: int = 0
        self.errors: int = 0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def put_on_cooldown(self, seconds: float):
        self.cooldown_until = time.time() + seconds
        self.backoff = min(self.backoff * 2, 120.0)

    def reset_backoff(self):
        self.backoff = max(5.0, self.backoff * 0.5)


class FleetManager:
    """
    Upravljanje rojem API ključeva za višestruke LLM provajdere.

    Struktura fleet:
        { "GEMINI": { "key_str": _KeyState, ... }, "GROQ": { ... }, ... }
    """

    def __init__(self, config_path: str = "dev_api.json"):
        # fleet je javni atribut jer ga drugi moduli direktno čitaju
        self.fleet: dict[str, dict[str, _KeyState]] = {}
        self._models: dict[str, str] = dict(_DEFAULT_MODELS)
        self._provider_backoff: dict[str, float] = {}
        self._load(config_path)

    # ------------------------------------------------------------------ #
    # Učitavanje konfiguracije
    # ------------------------------------------------------------------ #
    def _load(self, config_path: str):
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        try:
            path = Path(config_path)
            if not path.exists():
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        for provider, value in data.items():
            if provider.upper() in skip:
                continue
            prov_upper = provider.upper()

            # Podrška za dva formata:
            # Format A (jednostavni): "GEMINI": ["key1", "key2"]
            # Format B (prošireni):   "GEMINI": {"keys": [...], "model": "..."}
            if isinstance(value, list):
                keys = [k for k in value if isinstance(k, str) and k.strip()]
                model = _DEFAULT_MODELS.get(prov_upper)
            elif isinstance(value, dict):
                keys = [k for k in value.get("keys", []) if isinstance(k, str) and k.strip()]
                model = value.get("model") or _DEFAULT_MODELS.get(prov_upper)
            else:
                continue

            if not keys:
                continue

            self.fleet[prov_upper] = {k: _KeyState(k) for k in keys}
            if model:
                self._models[prov_upper] = model

    # ------------------------------------------------------------------ #
    # Odabir najboljeg ključa
    # ------------------------------------------------------------------ #
    def get_best_key(self, provider: str) -> str | None:
        """Vraća napremijer dostupan API ključ za provajdera, ili None."""
        prov_upper = provider.upper()
        bucket = self.fleet.get(prov_upper)
        if not bucket:
            return None
        available = [s for s in bucket.values() if s.is_available]
        if not available:
            return None
        # Preferiraj ključ s najmanje grešaka
        chosen = min(available, key=lambda s: s.errors)
        return chosen.key

    # ------------------------------------------------------------------ #
    # Analiza HTTP odgovora (rate-limit headeri)
    # ------------------------------------------------------------------ #
    def analyze_response(self, provider: str, key: str, status_code: int, headers):
        """Ažurira stanje ključa na osnovu HTTP statusa i headera."""
        prov_upper = provider.upper()
        bucket = self.fleet.get(prov_upper, {})
        state = bucket.get(key)
        if state is None:
            return

        state.total_requests += 1

        if status_code == 200:
            state.reset_backoff()
            return

        if status_code == 429:
            state.errors += 1
            # Pokušaj pročitati Retry-After header
            retry_after = 0.0
            for h in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset"):
                val = headers.get(h) if hasattr(headers, "get") else None
                if val:
                    try:
                        retry_after = float(val)
                        break
                    except (ValueError, TypeError):
                        pass
            cooldown = max(retry_after, _COOLDOWN_429)
            state.put_on_cooldown(cooldown)
            self._provider_backoff[prov_upper] = state.backoff

        elif status_code in (401, 403):
            # Ključ je nevažeći — stavi na dugi cooldown
            state.errors += 1
            state.put_on_cooldown(3600.0)

        elif status_code >= 500:
            state.errors += 1
            state.put_on_cooldown(_COOLDOWN_ERROR)

    # ------------------------------------------------------------------ #
    # Backoff po provajderu
    # ------------------------------------------------------------------ #
    def get_backoff_for_provider(self, provider: str) -> float:
        """Vraća preporučeno čekanje (s) za provajdera nakon rate-limita."""
        return self._provider_backoff.get(provider.upper(), 10.0)

    # ------------------------------------------------------------------ #
    # Aktivni model za provajdera
    # ------------------------------------------------------------------ #
    def get_active_model(self, provider: str) -> str | None:
        return self._models.get(provider.upper())

    # ------------------------------------------------------------------ #
    # Bilježenje korišćenja (za TTS modul)
    # ------------------------------------------------------------------ #
    def record_usage(self, provider: str, key: str, count: int = 1, success: bool = True):
        """Bilježi jedan ili više API poziva za dati ključ."""
        prov_upper = provider.upper()
        state = self.fleet.get(prov_upper, {}).get(key)
        if state is None:
            return
        state.total_requests += count
        if not success:
            state.errors += 1

    # ------------------------------------------------------------------ #
    # Sažetak flote (za /api/fleet endpoint i UI)
    # ------------------------------------------------------------------ #
    def get_fleet_summary(self) -> dict:
        """
        Vraća:
            { "GEMINI": {"active": N, "cooling": M, "total": T}, ... }
        """
        summary = {}
        for prov, bucket in self.fleet.items():
            active = sum(1 for s in bucket.values() if s.is_available)
            total = len(bucket)
            summary[prov] = {
                "active": active,
                "cooling": total - active,
                "total": total,
            }
        return summary
