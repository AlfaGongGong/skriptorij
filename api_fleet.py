# ============================================================================
# API FLEET MANAGER V10.3 — api_fleet.py
#
# ISPRAVKE v10.3:
#   BUG#1 FIX: auto-revive: now > cooldown_until (uklonjen pogrešan + 86400)
#   BUG#6 FIX: remaining_minute se resetuje kad prođe 60s od reset_time_minute
#   NOVO:       reset_time_minute se pravilno popunjava iz Retry-After headera
#   NOVO:       _reset_rpm_if_needed() poziva se u get_best_key() i available
# ============================================================================

import json
import time
import math
import threading
from pathlib import Path

# ── Dnevna kvota threshold (82800s = 23h)
_DAILY_QUOTA_RETRY_AFTER = 82800

_STATE_DEBOUNCE_INTERVAL = 30.0

_active_fleet = None


def register_active_fleet(fleet):
    global _active_fleet
    _active_fleet = fleet


def get_active_fleet():
    return _active_fleet


# ── Smart routing po ulozi
ROLE_PREFERRED_PROVIDERS = {
    "LEKTOR":    ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER", "CHUTES"],
    "KOREKTOR":  ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL"],
    "PREVODILAC":["GROQ", "CEREBRAS", "SAMBANOVA", "GEMINI", "MISTRAL"],
    "VALIDATOR": ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL"],
    "ANALIZA":   ["GEMINI", "GROQ", "CEREBRAS", "TOGETHER"],
    "GUARDIAN":  ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA"],
    "POLISH":    ["GEMINI", "MISTRAL", "COHERE", "TOGETHER"],
    "SCORER":    ["GEMINI", "MISTRAL", "OPENROUTER"],
}

# BUG#5 FIX: Preimenovano iz PROVIDER_PRIORITY u PROVIDER_ORDER
# da se izbjegne kolizija s network/provider_router.py koji ima
# PROVIDER_PRIORITY = {dict po ulozi}
PROVIDER_ORDER = [
    "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER",
    "FIREWORKS", "CHUTES", "GROQ", "CEREBRAS",
    "HUGGINGFACE", "KLUSTER", "OPENROUTER", "GITHUB", "GEMMA",
]

_DEFAULT_RPM = {
    "GEMINI": 15, "GROQ": 20, "CEREBRAS": 30, "SAMBANOVA": 10,
    "MISTRAL": 15, "COHERE": 15, "OPENROUTER": 20, "GITHUB": 10,
    "TOGETHER": 20, "FIREWORKS": 20, "CHUTES": 10,
    "HUGGINGFACE": 10, "KLUSTER": 15, "GEMMA": 10,
}

_DEFAULT_DAILY_QUOTA = {
    "GEMINI": 1500, "GROQ": 14400, "CEREBRAS": 14400, "SAMBANOVA": 10000,
    "MISTRAL": 1000, "GITHUB": 200, "COHERE": 1000, "OPENROUTER": 500,
    "TOGETHER": 1000, "FIREWORKS": 1000, "CHUTES": 1000,
    "HUGGINGFACE": 500, "KLUSTER": 500, "GEMMA": 500,
}

_AUTO_DISABLE_ERRORS   = 3
_AUTO_DISABLE_WINDOW   = 30
_AUTO_DISABLE_COOLDOWN = 300

_PROVIDER_GLOBAL_COOLDOWN = {
    "GEMINI": 8.0, "GROQ": 6.0, "CEREBRAS": 3.0, "SAMBANOVA": 10.0,
    "MISTRAL": 4.0, "COHERE": 4.0, "OPENROUTER": 4.0, "GITHUB": 8.0,
    "TOGETHER": 4.0, "FIREWORKS": 4.0, "CHUTES": 4.0,
    "HUGGINGFACE": 5.0, "KLUSTER": 5.0, "GEMMA": 6.0,
}

# RPM window u sekundama (Google resetuje svakih 60s)
_RPM_WINDOW = 60.0


class KeyState:
    """Stanje jednog API ključa."""

    def __init__(self, key: str, provider: str, saved: dict = None):
        self.key      = key
        self.provider = provider.upper()
        s = saved or {}

        self.is_active:  bool  = s.get("is_active", True)
        self.health:     float = s.get("health", 100.0)
        self.cooldown_until: float = s.get("cooldown_until", 0.0)
        self.req_rem:    int   = s.get("req_rem", _DEFAULT_DAILY_QUOTA.get(self.provider, 1000))
        self.disabled:   bool  = s.get("disabled", False)

        self.rate_limit_minute: int   = s.get("rate_limit_minute", _DEFAULT_RPM.get(self.provider, 20))
        self.remaining_minute:  int   = s.get("remaining_minute", self.rate_limit_minute)
        self.rate_limit_day:    int   = s.get("rate_limit_day", _DEFAULT_DAILY_QUOTA.get(self.provider, 1000))
        self.remaining_day:     int   = s.get("remaining_day", self.req_rem)

        # BUG#6 FIX: reset_time_minute = unix timestamp kad se RPM kvota resetuje
        # Inicijalno: sad + 60s (konzervativno)
        self.reset_time_minute: float = s.get("reset_time_minute", 0.0)

        self.total_requests: int   = s.get("total_requests", 0)
        self.errors:         int   = s.get("errors", 0)
        self.last_used:      float = s.get("last_used", 0.0)

        self._error_timestamps: list = []

    # ── BUG#6 FIX: RPM reset ────────────────────────────────────────────────

    def _reset_rpm_if_needed(self) -> None:
        """
        Resetuje remaining_minute ako je prošao RPM window (60s).
        Poziva se na svakom čitanju available i health_score.
        """
        now = time.time()
        # Ako je reset_time_minute 0 ili u prošlosti → obnovi RPM
        if self.reset_time_minute == 0.0 or now >= self.reset_time_minute:
            self.remaining_minute  = self.rate_limit_minute
            self.reset_time_minute = now + _RPM_WINDOW

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        if self.disabled or not self.is_active:
            return False
        if time.time() < self.cooldown_until:
            return False
        if self.req_rem <= 0:
            return False
        # BUG#6 FIX: resetuj RPM prije provjere
        self._reset_rpm_if_needed()
        return True

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    @property
    def health_score(self) -> float:
        # BUG#6 FIX: resetuj RPM prije računanja health_score
        self._reset_rpm_if_needed()
        rpm_pct = (self.remaining_minute / max(1, self.rate_limit_minute)) * 100
        rpd_pct = (self.remaining_day    / max(1, self.rate_limit_day))    * 100
        return round(
            0.5 * min(rpm_pct, 100) + 0.3 * min(rpd_pct, 100) + 0.2 * self.health, 1
        )

    @property
    def masked(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return self.key[:4] + "…" + self.key[-4:]

    # ── Error tracking ───────────────────────────────────────────────────────

    def record_error(self) -> bool:
        """Vrati True ako je auto-disabled."""
        now = time.time()
        self._error_timestamps.append(now)
        self._error_timestamps = [
            t for t in self._error_timestamps if now - t <= _AUTO_DISABLE_WINDOW
        ]
        self.errors += 1
        self.health  = max(0.0, self.health - 20)
        if len(self._error_timestamps) >= _AUTO_DISABLE_ERRORS:
            self.cooldown_until = now + _AUTO_DISABLE_COOLDOWN
            self._error_timestamps.clear()
            return True
        return False

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "is_active":         self.is_active,
            "health":            self.health,
            "cooldown_until":    self.cooldown_until,
            "req_rem":           self.req_rem,
            "disabled":          self.disabled,
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute":  self.remaining_minute,
            "rate_limit_day":    self.rate_limit_day,
            "remaining_day":     self.remaining_day,
            "total_requests":    self.total_requests,
            "errors":            self.errors,
            "last_used":         self.last_used,
            "reset_time_minute": self.reset_time_minute,
        }

    def to_ui_dict(self) -> dict:
        return {
            "key":               self.masked,
            "masked":            self.masked,
            "available":         self.available,
            "disabled":          self.disabled,
            "health":            round(self.health_score, 1),
            "cooldown_remaining": round(self.cooldown_remaining, 1),
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute":  self.remaining_minute,
            "rate_limit_day":    self.rate_limit_day,
            "remaining_day":     self.remaining_day,
            "total_requests":    self.total_requests,
            "errors":            self.errors,
        }


class FleetManager:
    """V10.3 Fleet Manager."""

    def __init__(self, config_path="dev_api.json", state_path="api_state.json"):
        self.config_path = Path(config_path)
        self.state_path  = Path(state_path)
        self.lock        = threading.Lock()
        self.fleet: dict = {}
        self.resolved_models: dict = {}
        self._rr_index: dict = {}
        self._last_call: dict = {}

        self._last_save_time: float = 0.0
        self._dirty: bool = False
        self._save_lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

        self._load_config()
        self._resolve_models()

    # ── Config & persistence ─────────────────────────────────────────────────

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
            self.fleet[prov_u]    = []
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
        """Modeli prema zvaničnoj dokumentaciji — Maj 2026."""
        self.resolved_models = {
            "CEREBRAS":    "gpt-oss-20b",
            "SAMBANOVA":   "DeepSeek-V3.1",
            "GROQ":        "llama-3.1-8b-instant",
            "GEMINI":      "gemini-2.0-flash",       # Primarni model za Gemini
            "MISTRAL":     "mistral-small-latest",
            "TOGETHER":    "meta-llama/Llama-3.2-3B-Instruct-Turbo",
            "OPENROUTER":  "meta-llama/llama-3.3-70b-instruct:free",
            "COHERE":      "command-r-08-2024",
            "CHUTES":      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            "HUGGINGFACE": "meta-llama/Meta-Llama-3-8B-Instruct",
            "KLUSTER":     "klusterai/Meta-Llama-3.1-8B-Instruct-Turbo",
        }

    def _save_state(self):
        with self._save_lock:
            self._dirty = True
            now     = time.time()
            elapsed = now - self._last_save_time
            if elapsed >= _STATE_DEBOUNCE_INTERVAL:
                self._flush_state()
            else:
                if self._debounce_timer is None or not self._debounce_timer.is_alive():
                    remaining = _STATE_DEBOUNCE_INTERVAL - elapsed
                    self._debounce_timer = threading.Timer(remaining, self._flush_state_safe)
                    self._debounce_timer.daemon = True
                    self._debounce_timer.start()

    def _flush_state(self):
        if not self._dirty:
            return
        state = {
            p: {ks.key: ks.to_dict() for ks in keys}
            for p, keys in self.fleet.items()
        }
        try:
            self.state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), "utf-8"
            )
            self._last_save_time = time.time()
            self._dirty = False
        except Exception:
            pass

    def _flush_state_safe(self):
        with self._save_lock:
            self._flush_state()

    def flush_now(self):
        with self._save_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            self._flush_state()

    def reload(self):
        with self.lock:
            self._load_config()
            self._resolve_models()

    def get_active_model(self, provider_upper: str) -> str:
        return self.resolved_models.get(provider_upper.upper(), "")

    # ── Key selection ────────────────────────────────────────────────────────

    def get_best_key(self, provider: str):
        """
        Vraća ključ s najboljim health score-om.

        BUG#1 FIX: auto-revive provjera je bila:
            now > ks.cooldown_until + 86400
        To znači da se ključ obnavljao tek 24h NAKON isteka cooldowna.
        Ispravno: ključ je aktivan čim mu istekne cooldown.
        """
        prov_u = provider.upper()
        with self.lock:
            keys = self.fleet.get(prov_u, [])
            if not keys:
                return None

            now = time.time()

            # BUG#1 FIX: auto-revive — obnovi ključeve kojima je cooldown ISTEKAO
            # Stari kod: now > ks.cooldown_until + 86400  ← POGREŠNO
            # Novi kod:  now > ks.cooldown_until           ← ISPRAVNO
            for ks in keys:
                if not ks.is_active and not ks.disabled:
                    if now > ks.cooldown_until:
                        ks.is_active       = True
                        ks.health          = max(ks.health, 30.0)
                        ks.cooldown_until  = 0.0
                        # Resetuj RPM kvotu
                        ks.remaining_minute  = ks.rate_limit_minute
                        ks.reset_time_minute = now + _RPM_WINDOW

            avail = [ks for ks in keys if ks.available]
            if not avail:
                return None

            avail.sort(key=lambda x: x.health_score, reverse=True)
            top_n  = max(1, math.ceil(len(avail) * 0.7))
            top    = avail[:top_n]
            idx    = self._rr_index.get(prov_u, 0) % len(top)
            chosen = top[idx]
            self._rr_index[prov_u] = (idx + 1) % len(top)
            return chosen.key

    def get_best_key_for_role(self, role: str):
        preferred = ROLE_PREFERRED_PROVIDERS.get(role.upper(), PROVIDER_ORDER)
        for prov in preferred:
            key = self.get_best_key(prov)
            if key:
                return prov, key
        for prov in PROVIDER_ORDER:  # BUG#5 FIX: bilo PROVIDER_PRIORITY
            if prov not in preferred:
                key = self.get_best_key(prov)
                if key:
                    return prov, key
        return None, None

    # ── Usage & error recording ───────────────────────────────────────────────

    def record_request(self, provider: str, key: str):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if ks:
                ks.total_requests   += 1
                ks.last_used         = time.time()
                ks.remaining_minute  = max(0, ks.remaining_minute - 1)
                ks.remaining_day     = max(0, ks.remaining_day - 1)
                ks.req_rem           = max(0, ks.req_rem - 1)
        self._save_state()

    def record_usage(self, provider: str, key: str, req_count: int = 1, success: bool = True):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return
            if success:
                ks.req_rem = max(0, ks.req_rem - req_count)
                ks.health  = min(100.0, ks.health + 2)
            else:
                ks.record_error()
        self._save_state()

    def analyze_response(self, provider: str, key: str, status_code: int, headers):
        """
        Parsira HTTP headere i ažurira KeyState.

        BUG#6 FIX: reset_time_minute se sada pravilno postavlja iz
        x-ratelimit-reset-requests headera ili kao now + 60s.
        """
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return
            h   = dict(headers) if headers else {}
            now = time.time()

            def hget(name):
                return h.get(name) or h.get(name.lower()) or h.get(name.upper())

            # RPM remaining
            for n in ["x-ratelimit-remaining-requests", "ratelimit-remaining", "x-remaining-requests"]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.remaining_minute = int(v)
                    except ValueError:
                        pass
                    break

            # RPM limit
            for n in ["x-ratelimit-limit-requests", "ratelimit-limit", "x-limit-requests"]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.rate_limit_minute = int(v)
                    except ValueError:
                        pass
                    break

            # RPD remaining
            for n in ["x-ratelimit-remaining-tokens-day", "x-ratelimit-remaining-day"]:
                v = hget(n)
                if v is not None:
                    try:
                        ks.remaining_day = int(v)
                        ks.req_rem       = ks.remaining_day
                    except ValueError:
                        pass
                    break

            # BUG#6 FIX: reset_time_minute iz headera
            for n in ["x-ratelimit-reset-requests", "ratelimit-reset", "retry-after"]:
                v = hget(n)
                if v is not None:
                    try:
                        reset_secs = float(v)
                        # Ako je to relativan offset (< 3600), dodaj na now
                        if reset_secs < 3600:
                            ks.reset_time_minute = now + reset_secs
                        # Ako je apsolutni timestamp, koristi direktno
                        elif reset_secs > now:
                            ks.reset_time_minute = reset_secs
                        else:
                            ks.reset_time_minute = now + _RPM_WINDOW
                    except ValueError:
                        ks.reset_time_minute = now + _RPM_WINDOW
                    break
            else:
                # Nema headera — postavi konzervativno
                if ks.reset_time_minute < now:
                    ks.reset_time_minute = now + _RPM_WINDOW

            # Status code handling
            if status_code == 200:
                ks.health = min(100.0, ks.health + 1)

            elif status_code in (429, 425):
                v  = hget("retry-after")
                ra = 60.0
                if v:
                    try:
                        ra = float(v)
                    except ValueError:
                        pass

                if ra > 3600:
                    # Dnevna kvota — dugi cooldown
                    ks.cooldown_until = now + min(ra, _DAILY_QUOTA_RETRY_AFTER)
                    ks.is_active      = False
                    ks.reset_time_minute = now + ra
                else:
                    # RPM limit — kratki cooldown
                    ks.cooldown_until    = now + max(ra, 5.0)
                    ks.reset_time_minute = now + max(ra, _RPM_WINDOW)

                ks.health = max(0.0, ks.health - 10)
                if ks.record_error():
                    ks.is_active = False

            elif status_code in (401, 403, 402, 412):
                # Nevažeći ključ — dugi cooldown (ali ne 30 dana — to je previše)
                ks.is_active      = False
                ks.health         = 0.0
                ks.cooldown_until = now + 86400  # 24h, ne 30 dana

            elif status_code >= 500:
                ks.record_error()

        self._save_state()

    # ── Helpers ──────────────────────────────────────────────────────────────

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
        return _PROVIDER_GLOBAL_COOLDOWN.get(provider.upper(), 4.0)

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
                ks.is_active         = True
                ks.cooldown_until    = 0.0
                ks.health            = max(ks.health, 30.0)
                ks.remaining_minute  = ks.rate_limit_minute
                ks.reset_time_minute = time.time() + _RPM_WINDOW
        self.flush_now()
        return {"ok": True, "disabled": ks.disabled, "provider": prov_u, "masked": ks.masked}

    def revive_all(self, provider: str = None) -> int:
        """
        Manualno oživljava sve ključeve kojima je cooldown istekao.
        Korisno za pozivanje iz UI-a ili pri startu.
        Vraća broj oživljenih ključeva.
        """
        count = 0
        now   = time.time()
        provs = [provider.upper()] if provider else list(self.fleet.keys())
        with self.lock:
            for prov_u in provs:
                for ks in self.fleet.get(prov_u, []):
                    if not ks.is_active and not ks.disabled and now > ks.cooldown_until:
                        ks.is_active         = True
                        ks.health            = max(ks.health, 30.0)
                        ks.cooldown_until    = 0.0
                        ks.remaining_minute  = ks.rate_limit_minute
                        ks.reset_time_minute = now + _RPM_WINDOW
                        count += 1
        if count:
            self.flush_now()
        return count

    # ── Fleet summary & UI ───────────────────────────────────────────────────

    def get_fleet_summary(self) -> dict:
        summary = {}
        for prov, keys in self.fleet.items():
            active  = sum(1 for k in keys if k.available)
            cooling = sum(
                1 for k in keys
                if not k.available and not k.disabled and k.cooldown_remaining > 0
            )
            summary[prov] = {
                "active":  active,
                "cooling": cooling,
                "total":   len(keys),
                "req_rem": sum(k.req_rem for k in keys),
            }
        return summary

    def get_fleet_ui(self) -> dict:
        result = {}
        for prov in PROVIDER_ORDER:  # BUG#5 FIX: bilo PROVIDER_PRIORITY
            keys = self.fleet.get(prov, [])
            if not keys:
                continue
            result[prov] = {
                "active": sum(1 for k in keys if k.available),
                "total":  len(keys),
                "keys":   [ks.to_ui_dict() for ks in keys],
            }
        for prov, keys in self.fleet.items():
            if prov not in result and keys:
                result[prov] = {
                    "active": sum(1 for k in keys if k.available),
                    "total":  len(keys),
                    "keys":   [ks.to_ui_dict() for ks in keys],
                }
        return result

    def get_total_active_keys(self) -> int:
        return sum(
            sum(1 for ks in keys if ks.available)
            for keys in self.fleet.values()
        )

    # ── Internal ─────────────────────────────────────────────────────────────

    def _find_key(self, prov_u: str, key_str: str):
        for ks in self.fleet.get(prov_u, []):
            if ks.key == key_str:
                return ks
        return None


# ── Google model pool ─────────────────────────────────────────────────────────
GOOGLE_MODEL_POOL = [
    {"model": "gemini-2.0-flash",      "rpm": 15, "rpd": 1500},
    {"model": "gemma-3-27b-it",        "rpm": 30, "rpd": 14400},
    {"model": "gemma-3-12b-it",        "rpm": 30, "rpd": 14400},
    {"model": "gemma-3-4b-it",         "rpm": 30, "rpd": 14400},
    {"model": "gemini-2.5-flash-lite", "rpm": 10, "rpd": 500},
]


def get_google_model_for_key(key_index):
    return GOOGLE_MODEL_POOL[key_index % len(GOOGLE_MODEL_POOL)]


def get_next_google_model(current_model):
    for i, m in enumerate(GOOGLE_MODEL_POOL):
        if m["model"] == current_model:
            return GOOGLE_MODEL_POOL[(i + 1) % len(GOOGLE_MODEL_POOL)]
    return GOOGLE_MODEL_POOL[0]