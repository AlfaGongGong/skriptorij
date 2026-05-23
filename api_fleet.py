# ============================================================================
# API FLEET MANAGER V12.0 — api_fleet.py
#
# V12.0: Reintegrisan QuotaTracker — per-key i per-provider praćenje:
#   • RPM (klizni 60s prozor), RPD (dnevni), TPD (dnevni tokeni)
#   • Cooldown po ključu (RPM 429 → Retry-After ili profil default)
#   • Cooldown dnevne kvote (RPD iscrpljen → do slijedećeg reseta)
#   • Provider-level cooldown (IP ban ili globalni 429)
#   • Greške po HTTP kodu praćene i u KeyState i u QuotaTracker
#   • get_best_key() sada poštuje availability iz QuotaTracker-a
#
# FIX 19.05.2026:
#   • GOOGLE_MODEL_POOL ažuriran — mrtvi modeli uklonjeni, živi dodani
#   • analyze_response: parsira retryDelay iz Google JSON body-a
#   • Ako nema retryDelay ali je RESOURCE_EXHAUSTED — cooldown do ponoći UTC
# ============================================================================

import json
import logging
import time
import math
import threading
from pathlib import Path

from config.system_logger import syslog
from network.quota_tracker import quota_tracker

logger = logging.getLogger(__name__)

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

PROVIDER_ORDER = [
    "GEMINI", "MISTRAL", "COHERE", "SAMBANOVA", "TOGETHER",
    "FIREWORKS", "CHUTES", "GROQ", "CEREBRAS",
    "HUGGINGFACE", "KLUSTER", "OPENROUTER", "GITHUB", "GEMMA",
]


class KeyState:
    """Stanje jednog API ključa — sadrži samo pozivne brojače."""

    def __init__(self, key: str, provider: str, saved: dict = None):
        self.key      = key
        self.provider = provider.upper()
        s = saved or {}

        self.total_requests: int   = s.get("total_requests", 0)
        self.last_used:      float = s.get("last_used", 0.0)

        self.calls_ok:       int  = s.get("calls_ok", 0)
        self.calls_failed:   int  = s.get("calls_failed", 0)
        self.calls_rejected: dict = {
            int(k): int(v)
            for k, v in s.get("calls_rejected", {}).items()
            if str(k).lstrip("-").isdigit()
        }

    @property
    def available(self) -> bool:
        ok, reason = quota_tracker.is_key_available(self.provider, self.key)
        if not ok:
            logger.debug(
                "[FleetManager] %s ...%s nedostupan: %s",
                self.provider, self.key[-4:], reason,
            )
        return ok

    def quota_info(self) -> dict:
        pq = quota_tracker._get_provider(self.provider)
        if not pq:
            return {}
        kq = pq.get_key(self.key)
        return kq.to_status_dict() if kq else {}

    @property
    def success_rate(self) -> float:
        total = self.calls_ok + self.calls_failed + sum(self.calls_rejected.values())
        if total == 0:
            return 1.0
        return round(self.calls_ok / total, 4)

    @property
    def masked(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return self.key[:4] + "…" + self.key[-4:]

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "last_used":      self.last_used,
            "calls_ok":       self.calls_ok,
            "calls_failed":   self.calls_failed,
            "calls_rejected": {str(k): v for k, v in self.calls_rejected.items()},
        }

    def to_ui_dict(self) -> dict:
        qi = self.quota_info()
        return {
            "key":            self.masked,
            "masked":         self.masked,
            "available":      self.available,
            "success_rate":   self.success_rate,
            "calls_ok":       self.calls_ok,
            "calls_failed":   self.calls_failed,
            "calls_rejected": {str(k): v for k, v in self.calls_rejected.items()},
            "total_requests": self.total_requests,
            "rpm":            qi.get("rpm_current", 0),
            "rpm_safe":       qi.get("rpm_safe", 0),
            "rpd":            qi.get("rpd_current", 0),
            "rpd_safe":       qi.get("rpd_safe", 0),
            "tpd":            qi.get("tpd_current", 0),
            "cooldown_s":     qi.get("cooldown_s", 0.0),
            "cooldown_reason": qi.get("cooldown_reason", ""),
        }


class FleetManager:
    """V12.0 Fleet Manager."""

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

    def _load_config(self):
        try:
            raw = json.loads(self.config_path.read_text("utf-8"))
            logger.debug("[FleetManager] Konfiguracija učitana iz %s", self.config_path)
        except Exception as e:
            logger.warning("[FleetManager] Nije moguće učitati konfiguraciju (%s): %s — flota prazna", self.config_path, e)
            raw = {}
        try:
            saved = json.loads(self.state_path.read_text("utf-8"))
            logger.debug("[FleetManager] Stanje ključeva učitano iz %s", self.state_path)
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
            logger.info("[FleetManager] %s: %d ključ(a) učitan(o)", prov_u, len(key_list))
            syslog.info("[FleetManager] %s: %d ključ(a) učitan(o)", prov_u, len(key_list))

        quota_tracker.initialize_from_fleet(self.fleet)
        syslog.info("[FleetManager] QuotaTracker inicijaliziran iz flote")

    def _resolve_models(self):
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
            logger.debug("[FleetManager] Stanje flushed u %s", self.state_path)
        except Exception as e:
            logger.error("[FleetManager] Nije moguće snimiti stanje u %s: %s", self.state_path, e)

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
        from network.model_discovery import get_cached_model
        prov = provider_upper.upper()
        discovered = get_cached_model(prov)
        if discovered:
            return discovered
        return self.resolved_models.get(prov, "")

    def get_best_key(self, provider: str):
        prov_u = provider.upper()
        with self.lock:
            keys = self.fleet.get(prov_u, [])
            if not keys:
                logger.warning("[FleetManager] get_best_key(%s): nema ključeva u floti", prov_u)
                syslog.warning("[FleetManager] get_best_key(%s): nema ključeva u floti", prov_u)
                return None

            available = [ks for ks in keys if ks.available]
            if not available:
                reasons = []
                for ks in keys:
                    ok, reason = quota_tracker.is_key_available(prov_u, ks.key)
                    reasons.append(f"...{ks.key[-4:]}: {reason}")
                syslog.warning(
                    "[FleetManager] %s: svi ključevi nedostupni — %s",
                    prov_u, " | ".join(reasons),
                )
                logger.warning(
                    "[FleetManager] get_best_key(%s): svi ključevi nedostupni (%d ključ(a))",
                    prov_u, len(keys),
                )
                return None

            # FIX: round-robin po svim dostupnim ključevima.
            # Prethodni kod: non_zero filter je excludovao sve ključeve s 0 ok/failed
            # (novi ključevi) pa je uvijek birao isti ključ koji je već imao uspjeha.
            # Rezultat: jedan ključ troši svu kvotu, ostali miruju.
            # Ispravak: RR po svim dostupnim ključevima, bez filtera po success_rate.
            # success_rate ostaje za logging i statistiku ali ne utječe na selekciju.
            idx    = self._rr_index.get(prov_u, 0) % len(available)
            chosen = available[idx]
            self._rr_index[prov_u] = (idx + 1) % len(available)
            logger.debug(
                "[FleetManager] get_best_key(%s): odabran ...%s (success_rate=%.2f, %d/%d dostupno)",
                prov_u, chosen.key[-4:], chosen.success_rate, len(available), len(keys),
            )
            syslog.debug(
                "[FleetManager] get_best_key(%s): odabran ...%s (sr=%.2f, %d/%d dostupno)",
                prov_u, chosen.key[-4:], chosen.success_rate, len(available), len(keys),
            )
            return chosen.key

    def get_best_key_for_role(self, role: str):
        preferred = ROLE_PREFERRED_PROVIDERS.get(role.upper(), PROVIDER_ORDER)
        for prov in preferred:
            key = self.get_best_key(prov)
            if key:
                logger.debug("[FleetManager] get_best_key_for_role(%s): odabran %s ...%s",
                             role, prov, key[-4:])
                return prov, key
        for prov in PROVIDER_ORDER:
            if prov not in preferred:
                key = self.get_best_key(prov)
                if key:
                    logger.debug("[FleetManager] get_best_key_for_role(%s) fallback: %s ...%s",
                                 role, prov, key[-4:])
                    return prov, key
        logger.warning("[FleetManager] get_best_key_for_role(%s): nema dostupnih ključeva ni za jedan provajder", role)
        return None, None

    def record_request(self, provider: str, key: str):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if ks:
                ks.total_requests += 1
                ks.last_used       = time.time()
        self._save_state()

    def record_usage(self, provider: str, key: str, req_count: int = 1, success: bool = True):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return
            if success:
                ks.calls_ok += req_count
            else:
                ks.calls_failed += 1
        self._save_state()

    def record_network_failure(self, provider: str, key: str):
        prov_u = provider.upper()
        with self.lock:
            ks = self._find_key(prov_u, key)
            if ks:
                ks.calls_failed += 1
        self._save_state()

    def analyze_response(self, provider: str, key: str, status_code: int, headers, body=None):
        """
        Ažurira pozivne brojače ključa prema HTTP status kodu.
        Poziva QuotaTracker koji upravlja cooldown-om i kvotama.
        """
        prov_u = provider.upper()

        # Izvuci tokene iz body-a
        tokens = 0
        if isinstance(body, dict):
            usage = body.get("usage", {})
            if isinstance(usage, dict):
                tokens = int(usage.get("total_tokens", 0) or 0)
                if tokens == 0:
                    tokens = int(
                        (usage.get("prompt_tokens") or 0) +
                        (usage.get("completion_tokens") or 0)
                    )

        # Izvuci Retry-After iz headera
        retry_after = None
        if headers:
            for hdr in ("Retry-After", "retry-after", "x-ratelimit-reset-requests"):
                val = headers.get(hdr)
                if val:
                    try:
                        retry_after = float(val)
                    except (TypeError, ValueError):
                        pass
                    break

        # FIX: Google Gemini ne šalje Retry-After header za RPD — šalje retryDelay u JSON body-u
        # Format: {"error": {"details": [{"retryDelay": "86400s"}]}}
        if retry_after is None and status_code == 429 and isinstance(body, dict):
            try:
                details = body.get("error", {}).get("details", [])
                for d in details:
                    rd = d.get("retryDelay", "")
                    if rd and isinstance(rd, str) and rd.endswith("s"):
                        retry_after = float(rd[:-1])
                        logger.info(
                            "[FleetManager] %s ...%s retryDelay iz body-a: %.0fs",
                            prov_u, key[-4:], retry_after,
                        )
                        break
            except Exception:
                pass

            # Ako je RESOURCE_EXHAUSTED bez retryDelay — cooldown do ponoći UTC + 1 min buffer
            if retry_after is None:
                import datetime
                err_msg    = str(body.get("error", {}).get("message", "")).lower()
                err_status = str(body.get("error", {}).get("status",  "")).lower()
                if "resource_exhausted" in err_status or "quota" in err_msg:
                    utc_now  = datetime.datetime.utcnow()
                    midnight = (utc_now + datetime.timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    retry_after = (midnight - utc_now).total_seconds() + 60.0
                    logger.info(
                        "[FleetManager] %s ...%s RESOURCE_EXHAUSTED bez retryDelay "
                        "— cooldown do ponoći UTC: %.0fs (%.1fh)",
                        prov_u, key[-4:], retry_after, retry_after / 3600,
                    )
                    syslog.warning(
                        "[FleetManager] %s ...%s GEMINI RPD iscrpljen "
                        "— automatski cooldown %.1fh do ponoći UTC",
                        prov_u, key[-4:], retry_after / 3600,
                    )

                # FIX 21.05.2026: RATE_LIMIT_EXCEEDED (RPM 429) — nema retryDelay ni header.
                # Gemini šalje ovaj status za RPM prekoračenje. Bez cooldowna → burst → 401 ban.
                # Koristimo cooldown_429_s iz profila (12s za Gemini).
                elif "rate_limit_exceeded" in err_status or "rate limit" in err_msg:
                    try:
                        from network.provider_profiles import get_cooldown_429
                        retry_after = get_cooldown_429(prov_u)
                    except Exception:
                        retry_after = 15.0
                    logger.info(
                        "[FleetManager] %s ...%s RATE_LIMIT_EXCEEDED bez retryDelay "
                        "— cooldown iz profila: %.0fs",
                        prov_u, key[-4:], retry_after,
                    )
                    syslog.warning(
                        "[FleetManager] %s ...%s RPM 429 RATE_LIMIT_EXCEEDED "
                        "— cooldown %.0fs",
                        prov_u, key[-4:], retry_after,
                    )

        # QuotaTracker — cooldown, kvote, tokeni
        quota_tracker.record_response(
            provider=prov_u,
            key=key,
            status_code=status_code,
            tokens=tokens,
            retry_after=retry_after,
            headers=headers,
        )

        with self.lock:
            ks = self._find_key(prov_u, key)
            if not ks:
                return

            if status_code == 200:
                ks.calls_ok += 1
                logger.debug(
                    "[FleetManager] %s ...%s → 200 OK (ok=%d, tokeni=%d)",
                    prov_u, key[-4:], ks.calls_ok, tokens,
                )
                syslog.debug(
                    "[FleetManager] %s ...%s → 200 OK (ok=%d, tokeni=%d)",
                    prov_u, key[-4:], ks.calls_ok, tokens,
                )
            elif status_code >= 500:
                ks.calls_failed += 1
                logger.warning(
                    "[FleetManager] %s ...%s → %d server error (failed=%d)",
                    prov_u, key[-4:], status_code, ks.calls_failed,
                )
                syslog.warning(
                    "[FleetManager] %s ...%s → %d server error (failed=%d)",
                    prov_u, key[-4:], status_code, ks.calls_failed,
                )
            elif status_code >= 400:
                ks.calls_rejected[status_code] = ks.calls_rejected.get(status_code, 0) + 1
                logger.warning(
                    "[FleetManager] %s ...%s → %d odbijen (rejected[%d]=%d)",
                    prov_u, key[-4:], status_code, status_code,
                    ks.calls_rejected[status_code],
                )
                syslog.warning(
                    "[FleetManager] %s ...%s → %d odbijen (rejected[%d]=%d, retry_after=%s)",
                    prov_u, key[-4:], status_code, status_code,
                    ks.calls_rejected[status_code],
                    f"{retry_after:.0fs}" if retry_after else "n/a",
                )

        self._save_state()

    def get_fleet_summary(self) -> dict:
        with self.lock:
            summary = {}
            for prov, keys in self.fleet.items():
                summary[prov] = {
                    "total":        len(keys),
                    "calls_ok":     sum(k.calls_ok for k in keys),
                    "calls_failed": sum(k.calls_failed for k in keys),
                }
        return summary

    @staticmethod
    def _prov_ui_entry(keys: list) -> dict:
        ui_keys = [ks.to_ui_dict() for ks in keys]
        sr = round(sum(k["success_rate"] for k in ui_keys) / len(ui_keys), 4) if ui_keys else 1.0
        return {"total": len(keys), "success_rate": sr, "keys": ui_keys}

    def get_fleet_ui(self) -> dict:
        with self.lock:
            result = {}
            for prov in PROVIDER_ORDER:
                keys = self.fleet.get(prov, [])
                if not keys:
                    continue
                result[prov] = self._prov_ui_entry(keys)
            for prov, keys in self.fleet.items():
                if prov not in result and keys:
                    result[prov] = self._prov_ui_entry(keys)
        return result

    def get_total_active_keys(self) -> int:
        with self.lock:
            return sum(len(keys) for keys in self.fleet.values())

    def _find_key(self, prov_u: str, key_str: str):
        for ks in self.fleet.get(prov_u, []):
            if ks.key == key_str:
                return ks
        return None


# ── Google model pool ─────────────────────────────────────────────────────────
# Sinkronizirano s http_client.py::_GOOGLE_MODEL_POOL_FALLBACK (22.05.2026)
#
# DEPRECATION STATUS:
#   gemini-2.0-flash      — DEPRECATED, shutdown 1. juna 2026 — IZBAČEN
#   gemini-2.5-flash/lite — deprecated okt 2026, ali RPD=1500 → fallback dok traju
#   gemini-3.1-flash-lite — STABLE, shutdown maj 2027
#   gemini-3.5-flash      — STABLE, nema shutdown datuma — PRIMARNI
#
# RPD (dashboard 22.05.2026): 3.x = 500/key, 2.5 = 1500/key
# Poredano: stable modeli prvi, deprecated fallback
GOOGLE_MODEL_POOL = [
    {"model": "gemini-3.5-flash",      "rpm": 10, "rpd": 500},   # #1 — STABLE, nema shutdown, best quality
    {"model": "gemini-3.1-flash-lite", "rpm": 15, "rpd": 500},   # #2 — STABLE, max throughput
    {"model": "gemini-2.5-flash-lite", "rpm": 15, "rpd": 1500},  # #3 — deprecated okt 2026, visok RPD
    {"model": "gemini-2.5-flash",      "rpm": 10, "rpd": 1500},  # #4 — deprecated okt 2026, bolji kvalitet
]


def get_google_model_for_key(key_index):
    return GOOGLE_MODEL_POOL[key_index % len(GOOGLE_MODEL_POOL)]


def get_next_google_model(current_model):
    for i, m in enumerate(GOOGLE_MODEL_POOL):
        if m["model"] == current_model:
            return GOOGLE_MODEL_POOL[(i + 1) % len(GOOGLE_MODEL_POOL)]
    return GOOGLE_MODEL_POOL[0]
