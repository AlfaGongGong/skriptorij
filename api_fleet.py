# ============================================================================
# API FLEET MANAGER V10.2 — api_fleet.py
# Kompatibilan s modularnim Skriptorij V10.2
#
# Implementirane optimizacije:
# #1  Smart routing — preferirani model po ulozi
# #2  Key health score — dinamički health na osnovu RPM+RPD
# #3  Auto-disable — 3 greške u 30s → cooldown 5 minuta
# #4  Round-robin rotacija ključeva po provajderu
# #5  Global cooldown tracker po provajderu
# #6  Prioritetni redosljed: GEMINI → MISTRAL → ...
# #7  Automatsko deaktiviranje neispravnih ključeva (402,403,401,412)
# ============================================================================

import json
import time
import math
import threading
from pathlib import Path

# ── Dnevna kvota threshold (82800s = 23h)
_DAILY_QUOTA_RETRY_AFTER = 82800

# ── Backwards compat — register_active_fleet poziva engine
_active_fleet = None


def register_active_fleet(fleet):
    global _active_fleet
    _active_fleet = fleet


def get_active_fleet():
    """Vraća aktivnu FleetManager instancu (registriranu od engine-a)."""
    return _active_fleet


# ── #1: Smart routing po ulozi
ROLE_PREFERRED_PROVIDERS = {
    "LEKTOR": ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER", "CHUTES"],
    "KOREKTOR": ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL"],
    "PREVODILAC": ["GROQ", "CEREBRAS", "SAMBANOVA", "GEMINI", "MISTRAL"],
    "VALIDATOR": ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL"],
    "ANALIZA": ["GEMINI", "GROQ", "CEREBRAS", "TOGETHER"],
    "GUARDIAN": ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA"],
    "POLISH": ["GEMINI", "MISTRAL", "COHERE", "TOGETHER"],
    "SCORER": ["GROQ", "CEREBRAS", "GEMINI"],
}

# ── #6: Globalni prioritetni redosljed
PROVIDER_PRIORITY = [
    "GEMINI",
    "MISTRAL",
    "COHERE",
    "SAMBANOVA",
    "TOGETHER",
    "FIREWORKS",
    "CHUTES",
    "GROQ",
    "CEREBRAS",
    "HUGGINGFACE",
    "KLUSTER",
    "OPENROUTER",
    "GITHUB",
    "GEMMA",
]

# ── Zadani RPM limiti (prepisuju se iz headera)
_DEFAULT_RPM = {
    "GEMINI": 15,
    "GROQ": 20,
    "CEREBRAS": 30,
    "SAMBANOVA": 20,
    "MISTRAL": 15,
    "COHERE": 15,
    "OPENROUTER": 20,
    "GITHUB": 10,
    "TOGETHER": 20,
    "FIREWORKS": 20,
    "CHUTES": 10,
    "HUGGINGFACE": 10,
    "KLUSTER": 15,
    "GEMMA": 10,
}

# ── Zadane dnevne kvote
_DEFAULT_DAILY_QUOTA = {
    "GEMINI": 1500,
    "GROQ": 14400,
    "CEREBRAS": 14400,
    "SAMBANOVA": 14400,
    "MISTRAL": 1000,
    "GITHUB": 200,
    "COHERE": 1000,
    "OPENROUTER": 500,
    "TOGETHER": 1000,
    "FIREWORKS": 1000,
    "CHUTES": 1000,
    "HUGGINGFACE": 500,
    "KLUSTER": 500,
    "GEMMA": 500,
}

# ── #3: Auto-disable parametri
_AUTO_DISABLE_ERRORS = 3
_AUTO_DISABLE_WINDOW = 30
_AUTO_DISABLE_COOLDOWN = 300

# ── #5: Global cooldown između poziva po provajderu
_PROVIDER_GLOBAL_COOLDOWN = {
    "GEMINI": 8.0,   # povećano zbog 429
    "GROQ": 6.0,     # povećano zbog 429
    "CEREBRAS": 3.0,
    "SAMBANOVA": 3.0,
    "MISTRAL": 4.0,
    "COHERE": 4.0,
    "OPENROUTER": 4.0,
    "GITHUB": 8.0,
    "TOGETHER": 4.0,
    "FIREWORKS": 4.0,
    "CHUTES": 4.0,
    "HUGGINGFACE": 5.0,
    "KLUSTER": 5.0,
    "GEMMA": 6.0,
}


class KeyState:
    """Stanje jednog API ključa — sve atribute koje V10 pristupa."""

    def __init__(self, key: str, provider: str, saved: dict = None):
        self.key = key
        self.provider = provider.upper()
        s = saved or {}

        # Core
        self.is_active: bool = s.get("is_active", True)
        self.health: float = s.get("health", 100.0)
        self.cooldown_until: float = s.get("cooldown_until", 0.0)
        self.req_rem: int = s.get(
            "req_rem", _DEFAULT_DAILY_QUOTA.get(self.provider, 1000)
        )
        self.disabled: bool = s.get("disabled", False)

        # Rate limit (iz HTTP headera)
        self.rate_limit_minute: int = s.get(
            "rate_limit_minute", _DEFAULT_RPM.get(self.provider, 20)
        )
        self.remaining_minute: int = s.get("remaining_minute", self.rate_limit_minute)
        self.rate_limit_day: int = s.get(
            "rate_limit_day", _DEFAULT_DAILY_QUOTA.get(self.provider, 1000)
        )
        self.remaining_day: int = s.get("remaining_day", self.req_rem)
        self.reset_time_minute: float = s.get("reset_time_minute", 0.0)

        # Stats
        self.total_requests: int = s.get("total_requests", 0)
        self.errors: int = s.get("errors", 0)
        self.last_used: float = s.get("last_used", 0.0)

        # #3: Sliding window za auto-disable
        self._error_timestamps: list = []

    @property
    def available(self) -> bool:
        if self.disabled or not self.is_active:
            return False
        if time.time() < self.cooldown_until:
            return False
        if self.req_rem <= 0:
            return False
        return True

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    @property
    def health_score(self) -> float:
        """#2: 50% RPM + 30% RPD + 20% bazni health."""
        rpm_pct = (self.remaining_minute / max(1, self.rate_limit_minute)) * 100
        rpd_pct = (self.remaining_day / max(1, self.rate_limit_day)) * 100
        return round(
            0.5 * min(rpm_pct, 100) + 0.3 * min(rpd_pct, 100) + 0.2 * self.health, 1
        )

    @property
    def masked(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return self.key[:4] + "…" + self.key[-4:]

    def record_error(self) -> bool:
        """#3: Vrati True ako je auto-disabled."""
        now = time.time()
        self._error_timestamps.append(now)
        self._error_timestamps = [
            t for t in self._error_timestamps if now - t <= _AUTO_DISABLE_WINDOW
        ]
        self.errors += 1
        self.health = max(0.0, self.health - 20)
        if len(self._error_timestamps) >= _AUTO_DISABLE_ERRORS:
            self.cooldown_until = now + _AUTO_DISABLE_COOLDOWN
            self._error_timestamps.clear()
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "is_active": self.is_active,
            "health": self.health,
            "cooldown_until": self.cooldown_until,
            "req_rem": self.req_rem,
            "disabled": self.disabled,
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute": self.remaining_minute,
            "rate_limit_day": self.rate_limit_day,
            "remaining_day": self.remaining_day,
            "total_requests": self.total_requests,
            "errors": self.errors,
            "last_used": self.last_used,
            "reset_time_minute": self.reset_time_minute,
        }

    def to_ui_dict(self) -> dict:
        """Format koji app.js fleet renderer očekuje."""
        return {
            "key": self.masked,
            "masked": self.masked,
            "available": self.available,
            "disabled": self.disabled,
            "health": round(self.health_score, 1),
            "cooldown_remaining": round(self.cooldown_remaining, 1),
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute": self.remaining_minute,
            "rate_limit_day": self.rate_limit_day,
            "remaining_day": self.remaining_day,
            "total_requests": self.total_requests,
            "errors": self.errors,
        }


class FleetManager:
    """V10.2 Fleet Manager. fleet = {PROV: [KeyState, ...]}"""

    def __init__(self, config_path="dev_api.json", state_path="api_state.json"):
        self.config_path = Path(config_path)
        self.state_path = Path(state_path)
        self.lock = threading.Lock()
        self.fleet: dict = {}
        self.resolved_models: dict = {}
        self._rr_index: dict = {}
        self._last_call: dict = {}
        self._load_config()
        self._resolve_models()

    # ── Config & persistence ────────────────────────────────────────────────

    def _load_config(self):
        try:
            raw = json.loads(self.config_path.read_text("utf-8"))
        except Exception:
            raw = {}
        try:
            saved = json.loads(self.state_path.read_text("utf-8"))
        except Exception:
            saved = {}

        for prov, data in raw.items():
            prov_u = prov.upper()
            if prov_u in {"EPUB_BACKGROUND", "PROXIES", "PROXIES_OFF"}:
                continue
            self.fleet[prov_u] = []
            self._rr_index[prov_u] = 0

            key_list = []
            if isinstance(data, list):
                key_list = [k.strip() for k in data if isinstance(k, str) and k.strip()]
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict) and "key" in v:
                        key_list.append(v["key"].strip())
                    elif isinstance(v, str) and v.strip():
                        key_list.append(v.strip())

            prov_saved = saved.get(prov_u, {})
            for k_str in key_list:
                self.fleet[prov_u].append(
                    KeyState(k_str, prov_u, prov_saved.get(k_str))
                )

    def _resolve_models(self):
        """Modeli prema zvaničnoj dokumentaciji – Maj 2026."""
        self.resolved_models = {
            "CEREBRAS": "mistralai/Mistral-Small-24B-Instruct-2501",
            "SAMBANOVA": "DeepSeek-V3.1",
            "GROQ": "llama-3.1-8b-instant",
            "GEMINI": "gemini-2.0-flash",
            "MISTRAL": "mistral-small-latest",
            "TOGETHER": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
            "OPENROUTER": "meta-llama/llama-3.3-70b-instruct:free",
            "COHERE": "command-r-08-2024",
            "CHUTES": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            "HUGGINGFACE": "meta-llama/Meta-Llama-3-8B-Instruct",
            "KLUSTER": "klusterai/Meta-Llama-3.1-8B-Instruct-Turbo",
        }
        self.fallback_models = {
            "CEREBRAS": ['mistralai/Mistral-Small-24B-Instruct-2501', 'zai-org/GLM-4.7', 'openai/gpt-oss-20b'],
            "SAMBANOVA": ['Meta-Llama-3.3-70B-Instruct', 'gpt-oss-120b', 'Llama-4-Maverick-17B-128E-Instruct'],
        }
    def _save_state(self):
        state = {
            p: {ks.key: ks.to_dict() for ks in keys} for p, keys in self.fleet.items()
        }
        try:
            self.state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), "utf-8"
            )
        except Exception:
            pass

    def reload(self):
        with self.lock:
            self._load_config()
            self._resolve_models()

    def get_active_model(self, provider_upper: str) -> str:
        return self.resolved_models.get(provider_upper.upper(), "")

    # ── Key selection ───────────────────────────────────────────────────────

    def get_best_key(self, provider: str):
        """#2 + #4: Top 70% health-score, round-robin."""
        prov_u = provider.upper()
        with self.lock:
            keys = self.fleet.get(prov_u, [])
            if not keys:
                return None
            now = time.time()
            # Auto-revive > 24h cooldown
            for ks in keys:
                if not ks.is_active and now > ks.cooldown_until + 86400:
                    ks.is_active = True
                    ks.health = 50.0
                    ks.req_rem = _DEFAULT_DAILY_QUOTA.get(prov_u, 1000)
                    ks.remaining_day = ks.req_rem
            avail = [ks for ks in keys if ks.available]
            if not avail:
                return None
            avail.sort(key=lambda x: x.health_score, reverse=True)
            top_n = max(1, math.ceil(len(avail) * 0.7))
            top = avail[:top_n]
            idx = self._rr_index.get(prov_u, 0) % len(top)
            chosen = top[idx]
            self._rr_index[prov_u] = (idx + 1) % len(top)
            return chosen.key

    def get_best_key_for_role(self, role: str):
        """#1: Smart routing — (provider, key) za datu ulogu."""
        preferred = ROLE_PREFERRED_PROVIDERS.get(role.upper(), PROVIDER_PRIORITY)
        for prov in preferred:
            key = self.get_best_key(prov)
            if key:
                return prov, key
        for prov in PROVIDER_PRIORITY:
            if prov not in preferred:
                key = self.get_best_key(prov)
                if key:
                    return prov, key
        return None, None

    # ── Usage & error recording ─────────────────────────────────────────────

    def record_request(self, provider: str, key: str):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if ks:
                ks.total_requests += 1
                ks.last_used = time.time()
                ks.remaining_minute = max(0, ks.remaining_minute - 1)
                ks.remaining_day = max(0, ks.remaining_day - 1)
                ks.req_rem = max(0, ks.req_rem - 1)

    def record_usage(
        self, provider: str, key: str, req_count: int = 1, success: bool = True
    ):
        """Backwards compat."""
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return
            if success:
                ks.req_rem = max(0, ks.req_rem - req_count)
                ks.health = min(100.0, ks.health + 2)
            else:
                ks.record_error()
            self._save_state()

    def analyze_response(self, provider: str, key: str, status_code: int, headers):
        """#5 + #7: Parsira HTTP headere i automatski deaktivira neispravne ključeve."""
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return
            h = dict(headers) if headers else {}

            def hget(name):
                return h.get(name) or h.get(name.lower()) or h.get(name.upper())

            for n in [
                "x-ratelimit-remaining-requests",
                "ratelimit-remaining",
                "x-remaining-requests",
            ]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.remaining_minute = int(v)
                    except ValueError:
                        pass
                    break

            for n in [
                "x-ratelimit-limit-requests",
                "ratelimit-limit",
                "x-limit-requests",
            ]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.rate_limit_minute = int(v)
                    except ValueError:
                        pass
                    break

            for n in ["x-ratelimit-remaining-tokens-day", "x-ratelimit-remaining-day"]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.remaining_day = int(v)
                        ks.req_rem = ks.remaining_day
                    except ValueError:
                        pass
                    break

            for n in ["retry-after", "x-ratelimit-reset-requests", "ratelimit-reset"]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.reset_time_minute = time.time() + float(v)
                    except ValueError:
                        pass
                    break

            if status_code == 200:
                ks.health = min(100.0, ks.health + 1)
            elif status_code in (429, 425):
                v = hget("retry-after")
                ra = 60.0
                if v:
                    try:
                        ra = float(v)
                        if ra > 3600:  # vjerovatno dnevni limit
                            ks.cooldown_until = time.time() + _DAILY_QUOTA_RETRY_AFTER
                            ks.is_active = False  # privremeno deaktiviraj do sutra
                    except ValueError:
                        pass
                if not ks.cooldown_until or ks.cooldown_until < time.time():
                    ks.cooldown_until = time.time() + max(ra, 5.0)
                ks.health = max(0.0, ks.health - 10)
                if ks.record_error():
                    ks.is_active = False
            elif status_code in (401, 403, 402, 412):
                # Trajno deaktiviraj – neispravan ključ, nema kredita ili zabranjen
                ks.is_active = False
                ks.health = 0.0
                ks.cooldown_until = time.time() + 86400 * 30  # mjesec dana
            elif status_code >= 500:
                ks.record_error()

    # ── RPM / backoff helpers ───────────────────────────────────────────────

    def get_rpm_used(self, provider: str, key: str) -> int:
        prov_u = provider.upper()
        ks = self._find_key(prov_u, key)
        return max(0, ks.rate_limit_minute - ks.remaining_minute) if ks else 0

    def get_effective_rpm_limit(self, provider: str, key: str) -> int:
        prov_u = provider.upper()
        ks = self._find_key(prov_u, key)
        return ks.rate_limit_minute if ks else 0

    def get_backoff_for_provider(self, provider: str) -> float:
        prov_u = provider.upper()
        cooldowns = [
            ks.cooldown_remaining
            for ks in self.fleet.get(prov_u, [])
            if ks.cooldown_remaining > 0
        ]
        return min(cooldowns) if cooldowns else 0.0

    def get_global_cooldown(self, provider: str) -> float:
        """#5: Min gap između poziva."""
        return _PROVIDER_GLOBAL_COOLDOWN.get(provider.upper(), 4.0)

    # ── Toggle ključa (iz UI) ───────────────────────────────────────────────

    def toggle_key(self, provider: str, key_val: str) -> dict:
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key_val)
            if not ks:
                for k in self.fleet.get(prov_u, []):
                    if k.masked == key_val:
                        ks = k
                        break
            if not ks:
                return {"error": "Ključ nije pronađen"}
            ks.disabled = not ks.disabled
            if not ks.disabled:
                ks.is_active = True
                ks.cooldown_until = 0.0
                ks.health = max(ks.health, 30.0)
            self._save_state()
            return {"ok": True, "disabled": ks.disabled, "provider": prov_u, "masked": ks.masked}

    # ── Fleet summary & UI ──────────────────────────────────────────────────

    def get_fleet_summary(self) -> dict:
        summary = {}
        for prov, keys in self.fleet.items():
            active = sum(1 for k in keys if k.available)
            cooling = sum(
                1
                for k in keys
                if not k.available and not k.disabled and k.cooldown_remaining > 0
            )
            summary[prov] = {
                "active": active,
                "cooling": cooling,
                "total": len(keys),
                "req_rem": sum(k.req_rem for k in keys),
            }
        return summary

    def get_fleet_ui(self) -> dict:
        """Format za /api/fleet — što app.js renderuje."""
        result = {}
        for prov in PROVIDER_PRIORITY:
            keys = self.fleet.get(prov, [])
            if not keys:
                continue
            result[prov] = {
                "active": sum(1 for k in keys if k.available),
                "total": len(keys),
                "keys": [ks.to_ui_dict() for ks in keys],
            }
        for prov, keys in self.fleet.items():
            if prov not in result and keys:
                result[prov] = {
                    "active": sum(1 for k in keys if k.available),
                    "total": len(keys),
                    "keys": [ks.to_ui_dict() for ks in keys],
                }
        return result

    def get_total_active_keys(self) -> int:
        return sum(
            sum(1 for ks in keys if ks.available) for keys in self.fleet.values()
        )

    # ── Internal ────────────────────────────────────────────────────────────

    def _find_key(self, prov_u: str, key_str: str):
        for ks in self.fleet.get(prov_u, []):
            if ks.key == key_str:
                return ks
        return None