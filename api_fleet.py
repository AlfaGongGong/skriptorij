# ============================================================================
# API FLEET MANAGER V10.4 — api_fleet.py
#
# ISPRAVKE v10.3:
#   BUG#1 FIX: auto-revive: now > cooldown_until (uklonjen pogrešan + 86400)
#   BUG#6 FIX: remaining_minute se resetuje kad prođe 60s od reset_time_minute
#   NOVO:       reset_time_minute se pravilno popunjava iz Retry-After headera
#   NOVO:       _reset_rpm_if_needed() poziva se u get_best_key() i available
#
# ISPRAVKE v10.4:
#   BUG#MODEL FIX: GOOGLE_MODEL_POOL ažuriran — uklonjeni dead preview modeli
#                  (gemini-2.5-flash-lite-preview-06-17, gemini-2.5-flash-preview-05-20
#                   vraćaju HTTP 404 od maja 2026).
#                  Novi pool: gemini-2.0-flash (primarni) → gemini-2.5-flash →
#                             gemini-2.0-flash-lite (živi modeli, provjereni).
# ============================================================================

import json
import re
import time
import math
import threading
from pathlib import Path

# ── Dnevna kvota threshold (82800s = 23h)
_DAILY_QUOTA_RETRY_AFTER = 82800


def _parse_groq_duration(value: str) -> float:
    """
    Parsira Groq-style duration stringove u sekunde.
    Groq šalje headere poput x-ratelimit-reset-tokens u ovim formatima:
      "2m59.56s"  →  179.56
      "7.66s"     →    7.66
      "30"        →   30.0    (plain broj, bez sufiksa)
    Vraća 0.0 ako format nije prepoznatljiv.
    """
    if not value:
        return 0.0
    s = value.strip()
    m = re.match(r'^(?:(\d+)m\s*)?(\d+(?:\.\d+)?)s?$', s)
    if m:
        minutes = float(m.group(1) or 0)
        seconds = float(m.group(2) or 0)
        return minutes * 60.0 + seconds
    try:
        return float(s)
    except ValueError:
        return 0.0

_STATE_DEBOUNCE_INTERVAL = 30.0

_active_fleet = None


def register_active_fleet(fleet):
    global _active_fleet
    _active_fleet = fleet


def get_active_fleet():
    return _active_fleet


# ── Smart routing po ulozi
ROLE_PREFERRED_PROVIDERS = {
    "LEKTOR":    ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER", "CHUTES", "GITHUB"],
    "KOREKTOR":  ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL", "GITHUB"],
    "PREVODILAC":["GROQ", "CEREBRAS", "SAMBANOVA", "GEMINI", "MISTRAL", "GITHUB"],
    "VALIDATOR": ["GROQ", "CEREBRAS", "GEMINI", "MISTRAL", "GITHUB"],
    "ANALIZA":   ["GEMINI", "GROQ", "CEREBRAS", "TOGETHER", "GITHUB"],
    "GUARDIAN":  ["GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "GITHUB"],
    "POLISH":    ["GEMINI", "MISTRAL", "COHERE", "TOGETHER", "GITHUB"],
    "SCORER":    ["GEMINI", "MISTRAL", "OPENROUTER", "GITHUB"],
}

# BUG#5 FIX: Preimenovano iz PROVIDER_PRIORITY u PROVIDER_ORDER
# da se izbjegne kolizija s network/provider_router.py koji ima
# PROVIDER_PRIORITY = {dict po ulozi}
PROVIDER_ORDER = [
    "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER",
    "FIREWORKS", "CHUTES", "GROQ", "CEREBRAS",
    "HUGGINGFACE", "KLUSTER", "OPENROUTER", "GITHUB", "GEMMA",
]

# ── Per-provider limiti i karakteristike ─────────────────────────────────────
# Svi limiti su centralizirani u network/provider_profiles.py.
# Ovdje importujemo samo ono što KeyState treba — ne dupliciramo podatke.
try:
    from network.provider_profiles import get_rpm_safe, get_rpd_safe, get_cooldown_429
    def _DEFAULT_RPM_GET(prov: str) -> int:
        return get_rpm_safe(prov)
    def _DEFAULT_QUOTA_GET(prov: str) -> int:
        return get_rpd_safe(prov) or 1000
    def _COOLDOWN_429_GET(prov: str) -> float:
        return get_cooldown_429(prov)
except ImportError:
    # Fallback ako provider_profiles.py nije još dostupan
    _RPM_FALLBACK = {
        "GEMINI": 12, "GROQ": 24, "CEREBRAS": 24, "SAMBANOVA": 8,
        "MISTRAL": 1,  "COHERE": 16, "OPENROUTER": 15, "GITHUB": 8,
        "TOGETHER": 16, "FIREWORKS": 16, "CHUTES": 8,
        "HUGGINGFACE": 7, "KLUSTER": 12, "GEMMA": 8,
    }
    _QUOTA_FALLBACK = {
        "GEMINI": 1275, "GROQ": 850, "CEREBRAS": 12000, "SAMBANOVA": 8500,
        "MISTRAL": 200,  "GITHUB": 42,  "COHERE": 850,  "OPENROUTER": 170,
        "TOGETHER": 850, "FIREWORKS": 850, "CHUTES": 3000,
        "HUGGINGFACE": 2000, "KLUSTER": 5000, "GEMMA": 500,
    }
    _COOLDOWN_FALLBACK = {
        "GEMINI": 65.0, "GROQ": 65.0, "SAMBANOVA": 70.0, "MISTRAL": 120.0,
        "COHERE": 65.0, "OPENROUTER": 70.0, "GITHUB": 70.0, "CHUTES": 70.0,
        "HUGGINGFACE": 90.0, "KLUSTER": 65.0, "GEMMA": 70.0,
    }
    def _DEFAULT_RPM_GET(prov: str) -> int:
        return _RPM_FALLBACK.get(prov.upper(), 10)
    def _DEFAULT_QUOTA_GET(prov: str) -> int:
        return _QUOTA_FALLBACK.get(prov.upper(), 1000)
    def _COOLDOWN_429_GET(prov: str) -> float:
        return _COOLDOWN_FALLBACK.get(prov.upper(), 65.0)

# _PROVIDER_GLOBAL_COOLDOWN je premješten u network/provider_profiles.py
# Koristimo get_cooldown_429() za per-provider kratki cooldown na 429.

# RPM window u sekundama (Google resetuje svakih 60s)
_RPM_WINDOW = 60.0

# Backward-compatible alias — vraća default dnevnu kvotu za provider
_DEFAULT_DAILY_QUOTA = _DEFAULT_QUOTA_GET


class KeyState:
    """Stanje jednog API ključa."""

    def __init__(self, key: str, provider: str, saved: dict = None):
        self.key      = key
        self.provider = provider.upper()
        s = saved or {}

        self.is_active:  bool  = s.get("is_active", True)
        self.cooldown_until: float = s.get("cooldown_until", 0.0)
        self.req_rem:    int   = s.get("req_rem", _DEFAULT_QUOTA_GET(self.provider))
        self.disabled:   bool  = s.get("disabled", False)

        self.rate_limit_minute: int   = s.get("rate_limit_minute", _DEFAULT_RPM_GET(self.provider))
        self.remaining_minute:  int   = s.get("remaining_minute", self.rate_limit_minute)
        self.rate_limit_day:    int   = s.get("rate_limit_day", _DEFAULT_QUOTA_GET(self.provider))
        self.remaining_day:     int   = s.get("remaining_day", self.req_rem)

        # BUG#6 FIX: reset_time_minute = unix timestamp kad se RPM kvota resetuje
        # Inicijalno: sad + 60s (konzervativno)
        self.reset_time_minute: float = s.get("reset_time_minute", 0.0)

        # BUG_D FIX: reset_time_minute učitan iz state fajla može biti u budućnosti
        # ako je server restartovan unutar RPM window-a (60s) od prethodne 429 greške.
        # U tom slučaju ključ bi ostao "unavailable" dok god taj timestamp nije dostignut.
        # Rješenje: pri učitavanju, ako je reset_time_minute > now + 120s, vjerovatno je
        # to ostatak starog cooldowna koji više nije relevantan za RPM — resetujemo ga.
        # Napomena: cooldown_until (dnevna kvota) se NE dira ovdje — to je ispravno.
        now_init = time.time()
        if self.reset_time_minute > now_init + 120.0:
            self.reset_time_minute = 0.0  # _reset_rpm_if_needed() će ga odmah obnoviti

        self.total_requests: int   = s.get("total_requests", 0)
        self.last_used:      float = s.get("last_used", 0.0)

        # ── Brojevni brojači poziva (zamjena za health float) ────────────────
        # calls_ok       : ukupno uspješnih HTTP 200 odgovora
        # calls_failed   : mrežne greške i timeoutovi (bez HTTP koda)
        # calls_rejected : HTTP greške po kodu — {429: 5, 401: 1, 500: 2, ...}
        #                  int ključevi u memoriji, string ključevi u JSON (auto-konverzija)
        self.calls_ok:       int       = s.get("calls_ok", 0)
        self.calls_failed:   int       = s.get("calls_failed", 0)
        self.calls_rejected: dict      = {
            int(k): int(v)
            for k, v in s.get("calls_rejected", {}).items()
        }

    # ── BUG#6 FIX: RPM reset ────────────────────────────────────────────────

    def _reset_rpm_if_needed(self) -> None:
        """
        Resetuje remaining_minute ako je prošao RPM window (60s).
        Poziva se na svakom čitanju available i success_rate.
        """
        now = time.time()
        # Ako je reset_time_minute 0 ili u prošlosti → obnovi RPM
        if self.reset_time_minute == 0.0 or now >= self.reset_time_minute:
            self.remaining_minute  = self.rate_limit_minute
            self.reset_time_minute = now + _RPM_WINDOW

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        now = time.time()
        if self.disabled:
            return False
        # Auto-revive kada istekne cooldown (štiti od "zaglavljivanja" u inactive).
        if not self.is_active:
            if now >= self.cooldown_until:
                self._reset_for_reactivation()
            else:
                return False
        if now < self.cooldown_until:
            return False
        # BUG #2 FIX: req_rem == 0 (dnevna kvota) — auto-revive kad cooldown istekne
        if self.req_rem <= 0:
            if now >= self.cooldown_until:
                self._reset_for_reactivation()
            else:
                return False
        # BUG#6 FIX: resetuj RPM prije provjere
        self._reset_rpm_if_needed()
        return True

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    @property
    def success_rate(self) -> float:
        """
        Stopa uspješnosti: calls_ok / ukupno poziva.
        Novi ključ (svi brojači == 0) → 1.0 (tretira se kao best-case da se odmah koristi).
        Koristi se za rangiranje ključeva u get_best_key i _call_gemini_with_full_rotation.
        """
        self._reset_rpm_if_needed()
        total = self.calls_ok + self.calls_failed + sum(self.calls_rejected.values())
        if total == 0:
            return 1.0
        return round(self.calls_ok / total, 4)

    @property
    def masked(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return self.key[:4] + "…" + self.key[-4:]

    def _reset_for_reactivation(self) -> None:
        """
        Resetuje stanje ključa za reaktivaciju (auto-revive ili manuelno uključivanje).
        Poziva se iz toggle_key, get_best_key, revive_all i available property-a.
        """
        now = time.time()
        self.is_active = True
        self.cooldown_until = 0.0
        self.remaining_minute = self.rate_limit_minute
        # BUG #5 FIX: uvijek postavi svježi timestamp — ne max() koji može zadržati
        # stari timestamp 23h u budućnosti (nastao od BUG #3) i blokirati RPM 23h.
        self.reset_time_minute = now + _RPM_WINDOW
        # req_rem se mogao postaviti na 0 od dnevne kvote 429 — resetuj ga
        if self.req_rem <= 0:
            self.req_rem = _DEFAULT_QUOTA_GET(self.provider)
            self.remaining_day = self.rate_limit_day

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "is_active":         self.is_active,
            "cooldown_until":    self.cooldown_until,
            "req_rem":           self.req_rem,
            "disabled":          self.disabled,
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute":  self.remaining_minute,
            "rate_limit_day":    self.rate_limit_day,
            "remaining_day":     self.remaining_day,
            "total_requests":    self.total_requests,
            "last_used":         self.last_used,
            "reset_time_minute": self.reset_time_minute,
            "calls_ok":          self.calls_ok,
            "calls_failed":      self.calls_failed,
            "calls_rejected":    {str(k): v for k, v in self.calls_rejected.items()},
        }

    def to_ui_dict(self) -> dict:
        return {
            "key":               self.masked,
            "masked":            self.masked,
            "available":         self.available,
            "disabled":          self.disabled,
            "success_rate":      self.success_rate,
            "calls_ok":          self.calls_ok,
            "calls_failed":      self.calls_failed,
            "calls_rejected":    {str(k): v for k, v in self.calls_rejected.items()},
            "cooldown_remaining": round(self.cooldown_remaining, 1),
            "rate_limit_minute": self.rate_limit_minute,
            "remaining_minute":  self.remaining_minute,
            "rate_limit_day":    self.rate_limit_day,
            "remaining_day":     self.remaining_day,
            "total_requests":    self.total_requests,
        }


# Ključne riječi u tijelu odgovora koje ukazuju na iscrpljenost kvote.
# Definisano jednom na nivou modula — koristi se i u _is_quota_exhausted_body()
# i može se importovati u network.model_discovery radi konzistentnosti.
_QUOTA_KEYWORDS = frozenset([
    "quota",               # Google RESOURCE_EXHAUSTED, general
    "insufficient_quota",  # OpenAI specifični kod greške
    "billing",             # Billing/account greška
    "daily limit",         # Dnevna kvota
    "monthly limit",       # Mjesečna kvota
    "out of credits",      # Sistemi na kredit
    "account balance",     # Stanje računa
    "prepaid",             # Prepaid kredit
    "resource exhausted",  # Google: RESOURCE_EXHAUSTED
])

# GEMINI specifična provjera: "quota" i "resource exhausted" se pojavljuju u SVIM
# Google 429 odgovorima — i RPM limitima i dnevnim kvotama. Za Gemini koristimo
# strožije ključne riječi koje jednoznačno ukazuju na BILLING/dnevnu kvotu,
# a ne na kratkoročni RPM limit koji se obnovi za 60 sekundi.
_GEMINI_BILLING_KEYWORDS = frozenset([
    "insufficient_quota",        # OpenAI/Google billing greška
    "billing",                   # Billing/account greška
    "daily limit",               # Dnevna kvota
    "monthly limit",             # Mjesečna kvota
    "out of credits",            # Kredit iscrpljen
    "account balance",           # Stanje računa
    "prepaid",                   # Prepaid kredit
    "your current quota",        # Google: "exceeded your current quota"
    "plan and billing",          # Google: "check your plan and billing"
    "check your plan",           # Google: billing/subscription link
])


def _is_quota_exhausted_body(body) -> bool:
    """
    Provjerava body odgovora na prisutnost ključnih riječi koje ukazuju
    na iscrpljenost kvote (za razliku od rate limita koji se obnovi za minutu).
    Koristi se u analyze_response() za bolju klasifikaciju 429 grešaka.
    """
    if not body:
        return False
    body_lower = str(body).lower()
    return any(kw in body_lower for kw in _QUOTA_KEYWORDS)


def _is_billing_exhausted_body(body) -> bool:
    """
    Strožija provjera za iscrpljenu DNEVNU/BILLING kvotu — namijenjena
    Google/Gemini provajderu koji šalje "quota" i "resource exhausted" u svim
    429 odgovorima, uključujući kratkoročne RPM limite.
    Vraća True samo ako body sadrži jasne pokazatelje billing/account problema.
    """
    if not body:
        return False
    body_lower = str(body).lower()
    return any(kw in body_lower for kw in _GEMINI_BILLING_KEYWORDS)


class FleetManager:
    """V10.4 Fleet Manager."""

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
        """
        Inicijalizira resolved_models iz FALLBACK_MODELS.
        Stvarni auto-discovery se pokreće pozadinski putem
        network.model_discovery.prime_cache_sync() i start_background_refresh().
        get_active_model() uvijek vraća najsvježiji auto-otkriveni model.
        """
        from network.model_discovery import FALLBACK_MODELS
        self.resolved_models = dict(FALLBACK_MODELS)

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
        """
        Vraća trenutno aktivan model za provajdera.
        Prioritet: auto-otkriveni model (discovery cache) > fallback iz resolved_models.
        """
        from network.model_discovery import get_cached_model
        prov = provider_upper.upper()
        discovered = get_cached_model(prov)
        if discovered:
            return discovered
        return self.resolved_models.get(prov, "")

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
                        ks._reset_for_reactivation()

            avail = [ks for ks in keys if ks.available]
            if not avail:
                return None

            avail.sort(key=lambda x: x.success_rate, reverse=True)
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
                ks.calls_ok += req_count
            else:
                ks.calls_failed += 1
        self._save_state()

    def record_network_failure(self, provider: str, key: str):
        """
        Bilježi mrežnu grešku ili timeout — bez HTTP koda.
        Povećava calls_failed brojač.
        Poziva se iz _async_http_post kad request ne stigne do servera.
        """
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if ks:
                ks.calls_failed += 1
        self._save_state()

    def analyze_response(self, provider: str, key: str, status_code: int, headers, body=None):
        """
        Parsira HTTP headere i response body te ažurira KeyState.

        BUG#6 FIX: reset_time_minute se sada pravilno postavlja iz
        x-ratelimit-reset-requests headera ili kao now + 60s.

        NOVO: prima opcionalni `body` (dict ili str) za bolju klasifikaciju 429:
          - Ako body sadrži ključne riječi kvote (quota, exceeded, billing...)
            tretira 429 kao dnevnu kvotu (dugi cooldown), čak i bez Retry-After.
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

            # ── GROQ: headeri imaju specifičnu semantiku per dokumentaciji ───────
            # x-ratelimit-limit-requests     → uvijek RPD (dnevna kvota), NE RPM
            # x-ratelimit-remaining-requests → uvijek RPD, NE RPM
            # x-ratelimit-reset-requests     → RPD reset u "Xm Ys" formatu
            # x-ratelimit-limit-tokens       → uvijek TPM (tokens/min), NE TPD
            # x-ratelimit-remaining-tokens   → TPM remaining
            # x-ratelimit-reset-tokens       → TPM reset u "Xs" formatu (≈ RPM window)
            if prov_u == "GROQ":
                v = hget("x-ratelimit-remaining-requests")
                if v is not None:
                    try:
                        ks.remaining_day = int(v)
                        ks.req_rem       = ks.remaining_day
                    except ValueError:
                        pass

                v = hget("x-ratelimit-limit-requests")
                if v is not None:
                    try:
                        ks.rate_limit_day = int(v)
                    except ValueError:
                        pass

                # TPM reset ≈ per-minute window reset — koristimo za reset_time_minute
                v = hget("x-ratelimit-reset-tokens")
                if v is not None:
                    secs = _parse_groq_duration(v)
                    if secs > 0:
                        ks.reset_time_minute = now + secs
                elif ks.reset_time_minute < now:
                    ks.reset_time_minute = now + _RPM_WINDOW

            else:
                # ── Generic header parsing za ostale provajdere ──────────────────
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

            # ── RPD remaining — zajednički za sve provajdere osim GROQ ──────────
            if prov_u != "GROQ":
                for n in ["x-ratelimit-remaining-tokens-day", "x-ratelimit-remaining-day"]:
                    v = hget(n)
                    if v is not None:
                        try:
                            ks.remaining_day = int(v)
                            ks.req_rem       = ks.remaining_day
                        except ValueError:
                            pass
                        break

            # Status code handling
            if status_code == 200:
                ks.calls_ok += 1

            elif status_code in (429, 425):
                ks.calls_rejected[status_code] = ks.calls_rejected.get(status_code, 0) + 1
                v  = hget("retry-after")
                ra = 60.0
                if v:
                    try:
                        ra = float(v)
                    except ValueError:
                        pass

                # Provjeri i body — neki provideri ne šalju Retry-After
                # ali body sadrži ključne riječi koje signaliziraju kvotu.
                # GEMINI poseban slučaj: Google šalje "quota" i "resource exhausted"
                # i za RPM limite i za dnevnu kvotu — koristimo strožu provjeru
                # koja traži eksplicitne billing/account pokazatelje.
                if prov_u in {"GEMINI", "GEMMA"}:
                    quota_body = _is_billing_exhausted_body(body)
                else:
                    quota_body = _is_quota_exhausted_body(body)

                if ra > 3600 or quota_body:
                    # Dnevna kvota — dugi cooldown
                    cooldown = min(ra, _DAILY_QUOTA_RETRY_AFTER) if ra > 3600 else _DAILY_QUOTA_RETRY_AFTER
                    ks.cooldown_until    = now + cooldown
                    ks.is_active         = False
                    # BUG #3 FIX: reset_time_minute je za RPM window (60s), ne dnevni cooldown.
                    # Postavljanje na 0.0 znači da će _reset_rpm_if_needed() odmah obnoviti
                    # RPM counter kad ključ dođe na auto-revive, umjesto da blokira 23h.
                    ks.reset_time_minute = 0.0
                    ks.req_rem           = 0
                    ks.remaining_day     = 0
                else:
                    # RPM limit — kratki per-provider cooldown iz profila
                    # (npr. Gemini=65s, Groq=65s, Mistral=120s, HuggingFace=90s ...)
                    provider_429_cd = _COOLDOWN_429_GET(prov_u)
                    effective_cd = max(ra, provider_429_cd) if ra > 0 else provider_429_cd
                    ks.cooldown_until    = now + effective_cd
                    ks.reset_time_minute = now + effective_cd

            elif status_code in (401, 403, 402, 412):
                # Nevažeći ključ — dugi cooldown
                ks.is_active      = False
                ks.cooldown_until = now + 86400  # 24h
                ks.calls_rejected[status_code] = ks.calls_rejected.get(status_code, 0) + 1

            elif status_code >= 500:
                ks.calls_failed += 1

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
        return _COOLDOWN_429_GET(provider.upper())

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
            now = time.time()

            # Ako je ključ auto-isključen (inactive, ali nije manualno disabled),
            # prvi klik ga treba vratiti online umjesto dodatnog "gašenja".
            if not ks.disabled and not ks.is_active:
                ks._reset_for_reactivation()
            else:
                ks.disabled = not ks.disabled
                if ks.disabled:
                    ks.is_active = False
                    ks.cooldown_until = 0.0
                else:
                    ks._reset_for_reactivation()
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
                    if ks.disabled:
                        continue
                    # BUG #8 FIX: Revivuj i ključeve gdje je req_rem=0 (dnevna kvota)
                    # ali je_active=True (nije prošao kroz is_active path)
                    if now > ks.cooldown_until and (not ks.is_active or ks.req_rem <= 0):
                        ks._reset_for_reactivation()
                        count += 1
        if count:
            self.flush_now()
        return count

    # ── Fleet summary & UI ───────────────────────────────────────────────────

    def get_fleet_summary(self) -> dict:
        # BUG-D FIX: self.fleet se čita bez locka — race condition s analyze_response()
        # Dodatno: ks.available MUTIRA stanje (poziva _reset_for_reactivation) — mora biti
        # pod lockom da ne vidi half-updated KeyState iz drugog threada.
        with self.lock:
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
        # BUG-D FIX: isti race condition kao get_fleet_summary — zaštiti s lockom.
        with self.lock:
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

    def force_reset_all(self, provider: str = None) -> int:
        """
        Prisilno resetuje SVE ključeve (bez obzira na cooldown ili is_active stanje).
        Korisno kad korisnik zna da su ključevi zdravi ali su pogrešno stavljeni
        na hlađenje (npr. zbog 429 koji je bio lažno klasificiran kao dnevna kvota).
        Vraća broj resetovanih ključeva.
        """
        count = 0
        provs = [provider.upper()] if provider else list(self.fleet.keys())
        with self.lock:
            for prov_u in provs:
                for ks in self.fleet.get(prov_u, []):
                    if ks.disabled:
                        continue
                    ks._reset_for_reactivation()
                    count += 1
        if count:
            self.flush_now()
        return count

    def get_total_active_keys(self) -> int:
        # BUG-D FIX: isti race condition — zaštiti s lockom.
        with self.lock:
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
# NAPOMENA: gemma-3-27b-it / 12b / 4b ugašeni od maja 2026 (HTTP 404) — uklonjeni.
# BUG#MODEL FIX: gemini-2.5-flash-lite-preview-06-17 i gemini-2.5-flash-preview-05-20
#   vraćaju HTTP 404 od maja 2026 — uklonjeni. Zamijenjeni živim modelima.
# Mora biti sinkronizirano s http_client.py::_GOOGLE_MODEL_POOL_FALLBACK.
GOOGLE_MODEL_POOL = [
    {"model": "gemini-2.0-flash",      "rpm": 15, "rpd": 1500},  # primarni — stabilan, visoki RPD
    {"model": "gemini-2.5-flash",      "rpm": 10, "rpd": 500},   # fallback 1 — noviji, stabilna GA verzija
    {"model": "gemini-2.0-flash-lite", "rpm": 30, "rpd": 1500},  # fallback 2 — visoki RPM, dobar za RPM hitove
]


def get_google_model_for_key(key_index):
    return GOOGLE_MODEL_POOL[key_index % len(GOOGLE_MODEL_POOL)]


def get_next_google_model(current_model):
    for i, m in enumerate(GOOGLE_MODEL_POOL):
        if m["model"] == current_model:
            return GOOGLE_MODEL_POOL[(i + 1) % len(GOOGLE_MODEL_POOL)]
    return GOOGLE_MODEL_POOL[0]
