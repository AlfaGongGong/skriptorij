"""network/quota_tracker.py

Per-ključ cooldown praćenje. Prati RPM/RPD iscrpljenost i cooldown stanje
svakog API ključa. Podaci se persistiraju na disk kako bi preživjeli restart.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_cooldown_429_s(provider: str) -> float:
    try:
        from config.ai_config import get_cooldown_429
        return get_cooldown_429(provider)
    except Exception:
        return 15.0


class KeyQuota:
    def __init__(self, key: str, provider: str):
        self.key = key
        self.provider = provider.upper()
        self._lock = threading.Lock()
        self._last_request_time: float = 0.0
        self._cooldown_until: float = 0.0
        self._cooldown_reason: str = ""
        self.errors: dict = {}
        self.min_gap_s: float = 2.0
        self._consecutive_401: int = 0

    def is_available(self) -> tuple:
        with self._lock:
            now = time.time()
            if self.min_gap_s > 0 and self._last_request_time > 0:
                elapsed = now - self._last_request_time
                if elapsed < self.min_gap_s:
                    return False, f"min_gap ({elapsed:.1f}s < {self.min_gap_s:.1f}s)"
            if self._cooldown_until > now:
                remaining = self._cooldown_until - now
                return False, f"cooldown {remaining:.0f}s ({self._cooldown_reason})"
            return True, ""

    def record_request(self):
        with self._lock:
            self._last_request_time = time.time()

    def record_success(self, tokens: int = 0):
        pass

    def record_error(self, status_code: int, retry_after: Optional[float] = None):
        with self._lock:
            self.errors[status_code] = self.errors.get(status_code, 0) + 1

            if status_code in (401, 402, 403):
                # 402 = Payment Required / ključ nevažeći (SambaNova i sl.)
                # 401/403 = neautoriziran / zabranjen pristup
                self._consecutive_401 = getattr(self, "_consecutive_401", 0) + 1
                if status_code == 402 or self._consecutive_401 >= 2:
                    self._set_cooldown(86400.0, f"ključ nevažeći ({status_code})")
                    logger.warning(
                        "[QuotaTracker] %s ...%s → %d (×%d) — ključ blacklistiran 24h",
                        self.provider, self.key[-4:], status_code, self._consecutive_401,
                    )
                else:
                    self._set_cooldown(300.0, f"401 privremeni cooldown (pokušaj {self._consecutive_401}/2)")
                    logger.warning(
                        "[QuotaTracker] %s ...%s → %d — kratki cooldown 5min (pokušaj %d/2)",
                        self.provider, self.key[-4:], status_code, self._consecutive_401,
                    )

            elif status_code == 429:
                if retry_after and retry_after > 3600:
                    cooldown_s = min(float(retry_after), 90000.0)
                    reason = "RPD kvota (dnevni limit)"
                    logger.warning(
                        "[QuotaTracker] %s ...%s → RPD EXHAUSTED — cooldown %.0fs (%.1fh)",
                        self.provider, self.key[-4:], cooldown_s, cooldown_s / 3600,
                    )
                elif retry_after and retry_after > 60:
                    cooldown_s = min(float(retry_after), 86400.0)
                    reason = "429 dugi cooldown"
                    logger.warning(
                        "[QuotaTracker] %s ...%s → 429 dugi cooldown %.0fs",
                        self.provider, self.key[-4:], cooldown_s,
                    )
                elif retry_after and retry_after > 0:
                    cooldown_s = min(float(retry_after), 120.0)
                    reason = "RPM 429 (Retry-After)"
                else:
                    cooldown_s = _get_cooldown_429_s(self.provider)
                    reason = f"RPM 429 (profil {cooldown_s:.0f}s)"
                    logger.info(
                        "[QuotaTracker] %s ...%s → 429 bez Retry-After — cooldown: %.0fs",
                        self.provider, self.key[-4:], cooldown_s,
                    )
                self._set_cooldown(cooldown_s, reason)

    def _set_cooldown(self, seconds: float, reason: str):
        new_until = time.time() + seconds
        if new_until > self._cooldown_until:
            self._cooldown_until = new_until
            self._cooldown_reason = reason

    def set_cooldown_external(self, seconds: float, reason: str = ""):
        with self._lock:
            self._set_cooldown(seconds, reason)

    def cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._cooldown_until - time.time())

    @property
    def current_rpm(self) -> int:
        return 0

    @property
    def current_rpd(self) -> int:
        return 0

    @property
    def current_tpd(self) -> int:
        return 0

    def to_status_dict(self) -> dict:
        with self._lock:
            cd = max(0.0, self._cooldown_until - time.time())
            return {
                "key_masked": self.key[-4:] if len(self.key) > 4 else "***",
                "provider": self.provider,
                "rpm_current": 0,
                "rpm_safe": 0,
                "rpd_current": 0,
                "rpd_safe": 0,
                "tpd_current": 0,
                "cooldown_s": round(cd, 1),
                "cooldown_reason": self._cooldown_reason if cd > 0 else "",
                "errors": dict(self.errors),
            }


class ProviderQuota:
    def __init__(self, provider: str):
        self.provider = provider.upper()
        self._lock = threading.Lock()
        self._keys: dict[str, KeyQuota] = {}
        # BUG #4 fix: provider-level cooldown stanje
        self._provider_cooldown_until: float = 0.0
        self._provider_cooldown_reason: str = ""

    def add_key(self, key: str, rpm_safe: int = 0, rpd_safe: int = 0, min_gap_s: float = 2.0) -> KeyQuota:
        with self._lock:
            if key not in self._keys:
                kq = KeyQuota(key, self.provider)
                kq.min_gap_s = min_gap_s
                self._keys[key] = kq
            return self._keys[key]

    def get_key(self, key: str) -> Optional[KeyQuota]:
        with self._lock:
            return self._keys.get(key)

    def get_available_keys(self) -> list:
        available = []
        with self._lock:
            for k, kq in self._keys.items():
                ok, _ = kq.is_available()
                if ok:
                    available.append((k, kq))
        return available

    def get_status_summary(self) -> dict:
        with self._lock:
            keys_status = [kq.to_status_dict() for kq in self._keys.values()]
        available = sum(1 for s in keys_status if s["cooldown_s"] == 0)
        with self._lock:
            prov_cd = max(0.0, self._provider_cooldown_until - time.time())
            prov_reason = self._provider_cooldown_reason
        return {
            "provider": self.provider,
            "provider_cooldown_s": round(prov_cd, 1),
            "provider_cooldown_reason": prov_reason,
            "total_keys": len(keys_status),
            "available_keys": available,
            "keys": keys_status,
        }

    def set_provider_cooldown(self, seconds: float, reason: str = ""):
        """BUG #4 fix: postavlja provider-level cooldown (bio no-op)."""
        new_until = time.time() + seconds
        with self._lock:
            if new_until > self._provider_cooldown_until:
                self._provider_cooldown_until = new_until
                self._provider_cooldown_reason = reason

    def provider_cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._provider_cooldown_until - time.time())


class QuotaTracker:
    # BUG #5 fix: apsolutna putanja — cooldowni više ne ovise o cwd()
    _PERSIST_PATH = str(Path(__file__).resolve().parent.parent / "quota_cooldowns.json")

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: dict[str, ProviderQuota] = {}

    def register_key(self, provider: str, key: str, rpm_safe: int = 15, rpd_safe: int = 1000, min_gap_s: float = 2.0):
        prov = provider.upper()
        with self._lock:
            if prov not in self._providers:
                self._providers[prov] = ProviderQuota(prov)
        self._providers[prov].add_key(key, rpm_safe, rpd_safe, min_gap_s)

    def initialize_from_fleet(self, fleet: dict):
        try:
            from config.ai_config import get_min_gap as _get_min_gap
        except ImportError:
            _get_min_gap = lambda p: 2.0  # noqa: E731

        for provider, key_states in fleet.items():
            prov_u = provider.upper()
            gap = _get_min_gap(prov_u)
            for ks in key_states:
                self.register_key(prov_u, ks.key, min_gap_s=gap)
                if prov_u == "GEMINI":
                    gemma_gap = _get_min_gap("GEMMA")
                    self.register_key("GEMMA", ks.key, min_gap_s=gemma_gap)
        logger.info("QuotaTracker inicijaliziran: %d provajdera", len(fleet))
        self._restore_cooldowns()

    def _restore_cooldowns(self):
        try:
            if not os.path.exists(self._PERSIST_PATH):
                return
            with open(self._PERSIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            restored = 0
            for prov, keys in data.items():
                for key, info in keys.items():
                    until = info.get("cooldown_until", 0)
                    reason = info.get("cooldown_reason", "")
                    if until > now:
                        remaining = until - now
                        pq = self._get_provider(prov)
                        kq = pq.get_key(key) if pq else None
                        if kq:
                            kq.set_cooldown_external(remaining, reason)
                            restored += 1
            if restored:
                logger.info("[QuotaTracker] Obnovljeno %d cooldown(a) s diska", restored)
        except Exception as e:
            logger.warning("[QuotaTracker] Nije moguće obnoviti cooldown stanje: %s", e)

    def _persist_cooldowns(self):
        now = time.time()
        data = {}
        with self._lock:
            for prov, pq in self._providers.items():
                with pq._lock:
                    for key, kq in pq._keys.items():
                        until = kq._cooldown_until
                        if until > now:
                            data.setdefault(prov, {})[key] = {
                                "cooldown_until": until,
                                "cooldown_reason": kq._cooldown_reason,
                            }
        try:
            with open(self._PERSIST_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("[QuotaTracker] Nije moguće snimiti cooldown stanje: %s", e)

    def record_request(self, provider: str, key: str):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.record_request()

    def record_response(self, provider: str, key: str, status_code: int,
                        tokens: int = 0, retry_after=None, headers=None):
        # BUG #7 fix: jedan lookup umjesto dva — thread-safer, bez duplog _get_provider
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if not kq:
            return
        if status_code == 200:
            with kq._lock:
                kq._consecutive_401 = 0
            kq.record_success(tokens)
        elif status_code >= 400:
            if retry_after is None and headers:
                ra = headers.get("Retry-After") or headers.get("retry-after")
                if ra:
                    try:
                        retry_after = float(ra)
                    except (TypeError, ValueError):
                        pass
            kq.record_error(status_code, retry_after)
            self._persist_cooldowns()

    def is_key_available(self, provider: str, key: str) -> tuple:
        pq = self._get_provider(provider.upper())
        if not pq:
            return True, ""
        kq = pq.get_key(key)
        if not kq:
            return True, ""
        return kq.is_available()

    def set_provider_cooldown(self, provider: str, seconds: float, reason: str = ""):
        pq = self._get_provider(provider.upper())
        if pq:
            pq.set_provider_cooldown(seconds, reason)
            self._persist_cooldowns()

    def set_key_cooldown(self, provider: str, key: str, seconds: float, reason: str = ""):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.set_cooldown_external(seconds, reason)
            self._persist_cooldowns()

    def get_provider_status(self, provider: str) -> Optional[dict]:
        pq = self._get_provider(provider.upper())
        return pq.get_status_summary() if pq else None

    def _get_provider(self, prov: str) -> Optional[ProviderQuota]:
        with self._lock:
            return self._providers.get(prov)


quota_tracker = QuotaTracker()
