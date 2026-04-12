# ============================================================================
# SKRIPTORIJ V8 — api_fleet.py
# Fleet Manager: upravljanje API ključevima, health tracking, backoff
# ============================================================================

import json
import os
import random
import time
from pathlib import Path
from typing import Optional

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

# ------------------------------------------------------------------ #
# Modul-razinski singleton — dijeli stanje s web endpointima
# ------------------------------------------------------------------ #
_active_fleet: Optional["FleetManager"] = None


def register_active_fleet(fm: "FleetManager") -> None:
    """Registrira aktivnu FleetManager instancu (poziva processing thread)."""
    global _active_fleet
    _active_fleet = fm


def get_active_fleet() -> Optional["FleetManager"]:
    """Vraća aktivnu FleetManager instancu, ili None ako nije registrovana."""
    return _active_fleet


class _KeyState:
    """Interno stanje jednog API ključa."""

    __slots__ = (
        "key",
        "cooldown_until",
        "backoff",
        "total_requests",
        "errors",
        # Rate limit info (minutni i dnevni limiti)
        "rate_limit_minute",
        "rate_limit_day",
        "remaining_minute",
        "remaining_day",
        # Praćenje zdravlja
        "last_success",
        "last_status_code",
        # Ručno onemogućen
        "disabled",
    )

    def __init__(self, key: str):
        self.key = key
        self.cooldown_until: float = 0.0
        self.backoff: float = 5.0
        self.total_requests: int = 0
        self.errors: int = 0
        self.rate_limit_minute: int = 0
        self.rate_limit_day: int = 0
        self.remaining_minute: int = -1
        self.remaining_day: int = -1
        self.last_success: float = 0.0
        self.last_status_code: int = 0
        self.disabled: bool = False

    @property
    def is_available(self) -> bool:
        return not self.disabled and time.time() >= self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        """Preostalo vrijeme hlađenja u sekundama (0 ako je dostupan)."""
        remaining = self.cooldown_until - time.time()
        return max(0.0, remaining)

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
        state.last_status_code = status_code

        def _hdr(name: str):
            """Čita header bez obzira na registar slova."""
            if not hasattr(headers, "get"):
                return None
            for h in (name, name.lower(), name.upper()):
                v = headers.get(h)
                if v is not None:
                    return v
            return None

        def _int_hdr(name: str) -> int:
            v = _hdr(name)
            if v is None:
                return -1
            try:
                return int(v)
            except (ValueError, TypeError):
                return -1

        # Parsiranje rate-limit headera (Gemini, Groq, OpenRouter, OpenAI stil)
        for minute_name in (
            "x-ratelimit-limit-requests",
            "x-ratelimit-limit-rpm",
            "ratelimit-limit",
        ):
            v = _int_hdr(minute_name)
            if v >= 0:
                state.rate_limit_minute = v
                break
        for minute_rem_name in (
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-rpm",
            "ratelimit-remaining",
        ):
            v = _int_hdr(minute_rem_name)
            if v >= 0:
                state.remaining_minute = v
                break
        for day_name in (
            "x-ratelimit-limit-tokens",
            "x-ratelimit-limit-rpd",
            "x-daily-limit",
        ):
            v = _int_hdr(day_name)
            if v >= 0:
                state.rate_limit_day = v
                break
        for day_rem_name in (
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-remaining-rpd",
            "x-daily-remaining",
        ):
            v = _int_hdr(day_rem_name)
            if v >= 0:
                state.remaining_day = v
                break

        if status_code == 200:
            state.last_success = time.time()
            state.reset_backoff()
            state.errors = 0
            return

        if status_code == 429:
            state.errors += 1
            # Pokušaj pročitati Retry-After header
            retry_after = 0.0
            for h in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset"):
                val = _hdr(h)
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
    # Ručno uključivanje / isključivanje ključa
    # ------------------------------------------------------------------ #
    def toggle_key(self, provider: str, key: str) -> bool | None:
        """
        Toggleuje disabled stanje ključa.
        Vraća novo stanje disabled (True=onemogućen, False=omogućen),
        ili None ako ključ nije pronađen.
        """
        prov_upper = provider.upper()
        state = self.fleet.get(prov_upper, {}).get(key)
        if state is None:
            return None
        state.disabled = not state.disabled
        return state.disabled

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
        if success:
            state.errors = 0
        else:
            state.errors += 1

    # ------------------------------------------------------------------ #
    # Sažetak flote (za /api/fleet endpoint i UI)
    # ------------------------------------------------------------------ #
    def get_fleet_summary(self) -> dict:
        """
        Vraća detaljan status flote po provajderu:
            {
              "GEMINI": {
                "active": N,
                "cooling": M,
                "total": T,
                "keys": [
                  {
                    "masked": "...abc123",
                    "available": true,
                    "cooldown_remaining": 0,
                    "total_requests": 42,
                    "errors": 1,
                    "rate_limit_minute": 60,
                    "remaining_minute": 55,
                    "rate_limit_day": 1000,
                    "remaining_day": 980,
                    "last_status_code": 200,
                    "last_success_ago": 5.3
                  }, ...
                ]
              }, ...
            }
        """
        now = time.time()
        summary = {}
        for prov, bucket in self.fleet.items():
            active = sum(1 for s in bucket.values() if s.is_available)
            total = len(bucket)
            keys_detail = []
            for s in bucket.values():
                masked = ("..." + s.key[-6:]) if len(s.key) > 6 else "***"
                last_ago = round(now - s.last_success, 1) if s.last_success else None
                keys_detail.append({
                    "masked": masked,
                    "key": s.key,
                    "available": s.is_available,
                    "disabled": s.disabled,
                    "cooldown_remaining": round(s.cooldown_remaining, 1),
                    "total_requests": s.total_requests,
                    "errors": s.errors,
                    "rate_limit_minute": s.rate_limit_minute if s.rate_limit_minute > 0 else None,
                    "remaining_minute": s.remaining_minute if s.remaining_minute != -1 else None,
                    "rate_limit_day": s.rate_limit_day if s.rate_limit_day > 0 else None,
                    "remaining_day": s.remaining_day if s.remaining_day != -1 else None,
                    "last_status_code": s.last_status_code if s.last_status_code else None,
                    "last_success_ago": last_ago,
                })
            summary[prov] = {
                "active": active,
                "cooling": total - active,
                "total": total,
                "keys": keys_detail,
            }
        return summary
