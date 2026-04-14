# ============================================================================
# SKRIPTORIJ V8 — api_fleet.py
# Fleet Manager: upravljanje API ključevima, health tracking, backoff
# ============================================================================

import json
import os
import random
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# Podrazumijevani modeli po provajderu
_DEFAULT_MODELS = {
    "GEMINI":      "gemini-flash-latest",
    "GROQ":        "llama-3.3-70b-versatile",
    "CEREBRAS":    "llama3.1-8b",
    "SAMBANOVA":   "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL":     "mistral-large-latest",
    "COHERE":      "command-a-03-2025",
    "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
    "GITHUB":      "Phi-4",
    "TOGETHER":    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS":   "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "CHUTES":      "deepseek-ai/DeepSeek-V3-0324",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER":     "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    # Gemma: bez sistemskog prompta i JSON moda — samo plaintext
    "GEMMA":       "gemma-3-27b-it",
}

# Cooldown nakon rate-limit greške (sekunde)
_COOLDOWN_429 = 90

# Konzervativni poznati free-tier RPM limiti po provajderu.
# Koriste se kada API ne vraća rate-limit headere (remaining_minute == -1).
# Postavljeni ispod stvarnih limita kao sigurnosna margina.
_KNOWN_FREE_RPM: dict[str, int] = {
    "GEMINI":      12,   # free tier: 15 RPM → koristimo 12
    "GROQ":        25,   # varira po modelu, konzervativna procjena
    "CEREBRAS":    25,
    "SAMBANOVA":   15,
    "MISTRAL":      4,   # free tier: veoma ograničen
    "COHERE":      15,
    "OPENROUTER":   8,   # free modeli: uski limiti
    "GITHUB":      12,   # GitHub Models: ~15 RPM
    "TOGETHER":    10,   # Together AI free tier: konzervativna procjena
    "FIREWORKS":   10,   # Fireworks AI free tier
    "CHUTES":      15,   # Chutes AI: liberalniji besplatni tier
    "HUGGINGFACE":  8,   # HF Inference API besplatni tier
    "KLUSTER":     10,   # Kluster AI besplatni tier
    "GEMMA":        5,   # Gemma via Together/Groq — konzervativna procjena
}

def _today_midnight_ts() -> float:
    """Vraća Unix timestamp ponoći tekućeg dana (lokalno)."""
    d = date.today()
    return datetime(d.year, d.month, d.day).timestamp()


_COOLDOWN_ERROR = 30
# Faktor eskalacije cooldowna po grešci i maksimalni cooldown/backoff
_COOLDOWN_ESCALATION = 1.5
_COOLDOWN_MAX = 600.0
_BACKOFF_MAX = 300.0

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
        # Dnevni reset — timestamp ponoći kada je dan zadnji put resetovan
        "day_reset_at",
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
        self.day_reset_at: float = _today_midnight_ts()
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
        # Eskalacija: svaka naredna 429 na istom ključu povećava cooldown
        # (_COOLDOWN_ESCALATION po grešci, max _COOLDOWN_MAX). Sprječava blokadu ključa.
        escalated = min(seconds * (_COOLDOWN_ESCALATION ** max(0, self.errors - 1)), _COOLDOWN_MAX)
        self.cooldown_until = time.time() + escalated
        self.backoff = min(self.backoff * 2, _BACKOFF_MAX)

    def reset_backoff(self):
        self.backoff = max(5.0, self.backoff * 0.5)

    def reset_day_if_needed(self) -> None:
        """Resetuje dnevnu kvotu ako je nastupila nova ponoć (lokalno)."""
        midnight = _today_midnight_ts()
        if midnight > self.day_reset_at:
            self.day_reset_at = midnight
            # Ako znamo ukupnu dnevnu kvotu, vrati je na maksimum
            if self.rate_limit_day > 0:
                self.remaining_day = self.rate_limit_day
            else:
                self.remaining_day = -1


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
        # Round-robin rotacija unutar iste tier-grupe ključeva
        self._key_rotation: dict[str, int] = {}
        # Interno praćenje zahtjeva: {key_str: [timestamp, ...]} — sliding window
        self._req_window: dict[str, list[float]] = {}
        self._config_path = config_path
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

    def reload(self, config_path: Optional[str] = None) -> None:
        """
        Osvježava fleet iz konfiguracijskog fajla bez gubljenja in-memory statistike.

        • Novi ključevi se dodaju s čistim _KeyState.
        • Postojeći ključevi zadržavaju cooldown, grešake, RPM prozor itd.
        • Ključevi koji su uklonjeni iz fajla brišu se iz fleet-a.
        • Provajderi s praznom listom ključeva se uklanjaju iz fleet-a (nestaju s dashboarda).
        """
        path = config_path or self._config_path
        skip = {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}
        try:
            p = Path(path)
            if not p.exists():
                return
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        seen_providers: set[str] = set()

        for provider, value in data.items():
            if provider.upper() in skip:
                continue
            prov_upper = provider.upper()

            if isinstance(value, list):
                keys = [k for k in value if isinstance(k, str) and k.strip()]
                model = _DEFAULT_MODELS.get(prov_upper)
            elif isinstance(value, dict):
                keys = [k for k in value.get("keys", []) if isinstance(k, str) and k.strip()]
                model = value.get("model") or _DEFAULT_MODELS.get(prov_upper)
            else:
                continue

            if not keys:
                # Provajder bez ključeva — ukloni iz fleet-a (postaje nevidljiv)
                self.fleet.pop(prov_upper, None)
                continue

            seen_providers.add(prov_upper)

            existing_bucket = self.fleet.get(prov_upper, {})
            new_bucket: dict[str, _KeyState] = {}
            for k in keys:
                # Sačuvaj postojeće stanje ako ključ već postoji, inače novi _KeyState
                new_bucket[k] = existing_bucket.get(k, _KeyState(k))
            self.fleet[prov_upper] = new_bucket

            if model:
                self._models[prov_upper] = model

        # Ukloni provajdere koji više nisu u fajlu
        for prov in list(self.fleet.keys()):
            if prov not in seen_providers:
                del self.fleet[prov]

    # ------------------------------------------------------------------ #
    # Odabir najboljeg ključa
    # ------------------------------------------------------------------ #
    def get_best_key(self, provider: str) -> str | None:
        """
        Vraća API ključ za provajdera koristeći round-robin rotaciju unutar
        tier-grupe s najmanje grešaka.  Ključevi se ravnomjerno dijele tako da
        se dnevna kvota troši proporcionalno, a ne samo na jednom ključu.
        """
        prov_upper = provider.upper()
        bucket = self.fleet.get(prov_upper)
        if not bucket:
            return None
        available = [s for s in bucket.values() if s.is_available]
        if not available:
            return None
        # Grupiši po broju grešaka — preferiraj ključeve s najmanje grešaka
        min_errors = min(s.errors for s in available)
        top_tier = [s for s in available if s.errors == min_errors]
        # Round-robin unutar top-tier: distribuira opterećenje
        idx = self._key_rotation.get(prov_upper, 0) % len(top_tier)
        self._key_rotation[prov_upper] = idx + 1
        return top_tier[idx].key

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

        # Resetuj dnevnu kvotu ako je nastupila nova ponoć
        state.reset_day_if_needed()

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
            "x-goog-quota-limit",          # Gemini REST API
        ):
            v = _int_hdr(minute_name)
            if v >= 0:
                state.rate_limit_minute = v
                break
        for minute_rem_name in (
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-rpm",
            "ratelimit-remaining",
            "x-goog-quota-remaining",      # Gemini REST API
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

        elif status_code == 425:
            # "Too Early" / overloaded — tretiramo kao blagu verziju rate-limita
            state.errors += 1
            state.put_on_cooldown(_COOLDOWN_429 // 2)
            self._provider_backoff[prov_upper] = state.backoff

        elif status_code in (401, 403):
            # Ključ je nevažeći — stavi na dugi cooldown
            state.errors += 1
            state.put_on_cooldown(3600.0)

        elif status_code == 412:
            # 412 = Precondition Failed — Fireworks: nalog suspendiran (billing/spending limit)
            # Trajni problem na razini naloga — onemogući ključ odmah
            state.errors += 1
            state.disabled = True

        elif status_code == 424:
            # 424 = Failed Dependency — GitHub: upstream greška veze (transijentna)
            # Tretiramo kao privremenu serversku grešku s cooldownom
            state.errors += 1
            state.put_on_cooldown(_COOLDOWN_ERROR)

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
    # Interno praćenje zahtjeva (RPM sliding window)
    # ------------------------------------------------------------------ #
    def record_request(self, provider: str, key: str) -> None:
        """
        Bilježi timestamp zahtjeva za dati ključ (RPM sliding window).
        Poziva se neposredno prije slanja HTTP zahtjeva, neovisno o HTTP statusu.
        """
        now = time.time()
        window = self._req_window.setdefault(key, [])
        window.append(now)
        # Zadrži samo zadnje 2 minute da spriječimo rast memorije
        self._req_window[key] = [t for t in window if now - t < 120.0]

    def get_rpm_used(self, provider: str, key: str) -> int:
        """Vraća broj zahtjeva poslatih ovim ključem u posljednjih 60 sekundi."""
        now = time.time()
        window = self._req_window.get(key, [])
        return sum(1 for t in window if now - t < 60.0)

    def get_effective_rpm_limit(self, provider: str, key: str) -> int:
        """
        Vraća efektivni RPM limit za dati ključ:
        • Ako su rate-limit headeri dostupni (rate_limit_minute > 0), koristi ih.
        • Inače, vraća konzervativni _KNOWN_FREE_RPM za provajdera.
        """
        prov_upper = provider.upper()
        state = self.fleet.get(prov_upper, {}).get(key)
        if state is not None and state.rate_limit_minute > 0:
            return state.rate_limit_minute
        return _KNOWN_FREE_RPM.get(prov_upper, 10)


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
        if not success:
            state.errors += 1
        else:
            state.errors = 0

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
                # Provjeri dnevni reset za svaki ključ (i pri dohvaćanju stanja)
                s.reset_day_if_needed()
                masked = ("..." + s.key[-6:]) if len(s.key) > 6 else "***"
                last_ago = round(now - s.last_success, 1) if s.last_success else None
                rpm_used = self.get_rpm_used(prov, s.key)
                rpm_limit = self.get_effective_rpm_limit(prov, s.key)
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
                    # Interno praćeni podaci (uvijek dostupni, neovisno o headerima)
                    "rpm_used_internal": rpm_used,
                    "rpm_limit_internal": rpm_limit,
                })

            # Ukupno dnevno zdravlje provajdera (% preostalog dnevnog kvota)
            keys_with_day = [
                s for s in bucket.values()
                if s.rate_limit_day > 0 and s.remaining_day >= 0
            ]
            if keys_with_day:
                day_health_pct = round(
                    sum(s.remaining_day for s in keys_with_day)
                    / sum(s.rate_limit_day for s in keys_with_day)
                    * 100
                )
            else:
                day_health_pct = None

            summary[prov] = {
                "active": active,
                "cooling": total - active,
                "total": total,
                "day_health_pct": day_health_pct,
                "keys": keys_detail,
            }
        return summary
