# network/quota_tracker.py
# ============================================================================
# QUOTA TRACKER V1.0 — Per-provider, per-key praćenje limita i hlađenja
#
# Prati za svaki ključ posebno, i za svaki provajder posebno:
#   • RPM  — zahtjevi u tekućoj minutnoj prozoru (60s klizni prozor)
#   • RPD  — zahtjevi u tekućem danu (reset u ponoć po UTC — ili po prvom
#             pozivu ako provajder ima custom reset prozor)
#   • TPD  — tokeni u tekućem danu (za provajdere koji imaju dnevni TPM limit)
#   • Greške po HTTP kodu — {429: N, 401: N, 500: N, ...}
#   • Cooldown po ključu — ključ se "hladi" onoliko koliko treba (ne fiksno)
#   • Cooldown po provideru — provider-level 429 backoff
#
# Reset periodi:
#   Većina provajdera resetuje kvote u ponoć UTC.
#   Google/Gemini resetuje RPD u ponoć US Pacific (UTC-8 ili UTC-7 DST).
#   Za sigurnost — koristimo UTC ponoć za sve, konzervativan pristup.
#   Svaki dnevni brojač pamti "datum reseta" — automatski se nuluje novi dan.
#
# Integracija:
#   • http_client.py → quota_tracker.record_request() prije slanja
#   • http_client.py → quota_tracker.record_response() nakon odgovora
#   • rate_limiter.py → quota_tracker.is_key_available() pri odabiru ključa
#   • api_fleet.py → KeyState.quota_info() za UI prikaz
# ============================================================================

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from config.system_logger import syslog

logger = logging.getLogger(__name__)

# ── Reset periodi po provideru (UTC sat reseta kvote) ───────────────────────
# Većina resetuje u ponoć UTC. Gemini resetuje u ponoć US Pacific ≈ 08:00 UTC.
# Konzervativno: koristimo 08:00 UTC za Gemini, 00:00 UTC za ostale.
_PROVIDER_RESET_HOUR_UTC: dict[str, int] = {
    "GEMINI": 8,    # ponoć US Pacific ≈ 08:00 UTC
    "GITHUB": 8,    # Microsoft/Azure — isto US Pacific
    "GROQ":   0,
    "CEREBRAS": 0,
    "SAMBANOVA": 0,
    "COHERE": 0,
    "OPENROUTER": 0,
    "KLUSTER": 0,
    "CHUTES": 0,
    "HUGGINGFACE": 0,
    "MISTRAL": 0,
    "TOGETHER": 0,
    "FIREWORKS": 0,
}

# ── Cooldown trajanje pri RPM 429 — provider može poslati Retry-After header,
# ali ako ne pošalje, koristimo profil iz provider_profiles.py.
# Pri DNEVNOJ kvoti (RPD iscrpljen) — ključ se hladi do slijedećeg reset sata.
# ─────────────────────────────────────────────────────────────────────────────


def _utc_day_key(reset_hour_utc: int = 0) -> str:
    """
    Vraća string koji identifikuje tekući "dan" za dati reset sat.
    Npr. ako reset_hour_utc=8, dan se mjenja u 08:00 UTC.
    Format: "YYYY-MM-DD@HH" gdje HH je reset sat.
    """
    now_utc = datetime.now(timezone.utc)
    # Ako smo prije reset sata — dan je "jučer" (još nismo resetovani)
    if now_utc.hour < reset_hour_utc:
        # Oduzmi jedan dan
        from datetime import timedelta
        effective_date = now_utc.date() - timedelta(days=1)
    else:
        effective_date = now_utc.date()
    return f"{effective_date.isoformat()}@{reset_hour_utc:02d}"


def _next_reset_timestamp(reset_hour_utc: int = 0) -> float:
    """Vraća Unix timestamp slijedećeg reset momenta za dati sat."""
    from datetime import timedelta
    now_utc = datetime.now(timezone.utc)
    # Slijedeći reset sat danas ili sutra
    reset_today = now_utc.replace(
        hour=reset_hour_utc, minute=0, second=0, microsecond=0
    )
    if now_utc >= reset_today:
        reset_today += timedelta(days=1)
    return reset_today.timestamp()


# ============================================================================
# KeyQuota — praćenje limita JEDNOG KLJUČA
# ============================================================================

class KeyQuota:
    """
    Prati RPM, RPD, TPD i greške za jedan API ključ.
    Thread-safe: svi pristupi su zaštićeni internim lock-om.
    """

    def __init__(self, key: str, provider: str, rpm_safe: int, rpd_safe: int):
        self.key         = key
        self.provider    = provider.upper()
        self.rpm_safe    = rpm_safe    # limit zahtjeva po minuti (za ovaj ključ)
        self.rpd_safe    = rpd_safe    # limit zahtjeva po danu (0 = neograničen)

        self._lock = threading.Lock()

        # RPM: klizni prozor (deque timestampova zadnjih 60s)
        self._rpm_window: deque[float] = deque()

        # RPD: dnevni brojač + datum reseta
        self._reset_hour = _PROVIDER_RESET_HOUR_UTC.get(self.provider, 0)
        self._rpd_day_key: str = _utc_day_key(self._reset_hour)
        self._rpd_count: int = 0

        # TPD: dnevni token brojač
        self._tpd_day_key: str = self._rpd_day_key
        self._tpd_count: int = 0

        # Greške po HTTP kodu
        self.errors: dict[int, int] = {}

        # Cooldown — ključ je "hladan" do ovog timestampa
        self._cooldown_until: float = 0.0
        self._cooldown_reason: str = ""

        # Ukupno odbijenih (429) u tekućem danu — za detekciju dnevne kvote
        self._daily_429_count: int = 0

    # ── Dnevni reset ─────────────────────────────────────────────────────────

    def _check_daily_reset(self):
        """Poziva se pod lock-om. Nuluje dnevne brojače ako je novi dan."""
        current_day = _utc_day_key(self._reset_hour)
        if current_day != self._rpd_day_key:
            old_rpd = self._rpd_count
            old_tpd = self._tpd_count
            self._rpd_day_key   = current_day
            self._rpd_count     = 0
            self._tpd_day_key   = current_day
            self._tpd_count     = 0
            self._daily_429_count = 0
            # Skini cooldown koji je bio zbog dnevne kvote
            if "RPD" in self._cooldown_reason or "dnevna" in self._cooldown_reason.lower():
                self._cooldown_until = 0.0
                self._cooldown_reason = ""
            syslog.info(
                "[quota] %s ...%s: dnevni reset — RPD bio %d, TPD bio %d",
                self.provider, self.key[-4:], old_rpd, old_tpd,
            )
            logger.info(
                "[quota] %s ...%s: dnevni reset (RPD=%d→0, TPD=%d→0)",
                self.provider, self.key[-4:], old_rpd, old_tpd,
            )

    # ── RPM prozor ───────────────────────────────────────────────────────────

    def _clean_rpm_window(self, now: float):
        """Uklanja timestampove starije od 60s iz RPM prozora. Pod lock-om."""
        cutoff = now - 60.0
        while self._rpm_window and self._rpm_window[0] < cutoff:
            self._rpm_window.popleft()

    @property
    def current_rpm(self) -> int:
        """Broj zahtjeva u zadnjih 60 sekundi."""
        with self._lock:
            self._clean_rpm_window(time.time())
            return len(self._rpm_window)

    @property
    def current_rpd(self) -> int:
        """Broj zahtjeva u tekućem danu."""
        with self._lock:
            self._check_daily_reset()
            return self._rpd_count

    @property
    def current_tpd(self) -> int:
        """Broj tokena u tekućem danu."""
        with self._lock:
            self._check_daily_reset()
            return self._tpd_count

    # ── Dostupnost ───────────────────────────────────────────────────────────

    def is_available(self) -> tuple[bool, str]:
        """
        Vraća (True, "") ako je ključ dostupan.
        Vraća (False, razlog) ako je hladan ili je potrošio kvotu.
        """
        with self._lock:
            now = time.time()
            self._check_daily_reset()

            # 1. Cooldown provjera
            if self._cooldown_until > now:
                remaining = self._cooldown_until - now
                reason = f"cooldown {remaining:.0f}s ({self._cooldown_reason})"
                return False, reason

            # 2. RPM provjera
            self._clean_rpm_window(now)
            if self.rpm_safe > 0 and len(self._rpm_window) >= self.rpm_safe:
                oldest = self._rpm_window[0] if self._rpm_window else now
                wait = max(0.0, (oldest + 60.0) - now)
                reason = f"RPM limit ({len(self._rpm_window)}/{self.rpm_safe}, čekanje {wait:.1f}s)"
                return False, reason

            # 3. RPD provjera
            if self.rpd_safe > 0 and self._rpd_count >= self.rpd_safe:
                next_reset = _next_reset_timestamp(self._reset_hour)
                remaining = max(0.0, next_reset - now)
                reason = f"RPD iscrpljen ({self._rpd_count}/{self.rpd_safe}, reset za {remaining/3600:.1f}h)"
                return False, reason

            return True, ""

    def cooldown_remaining(self) -> float:
        """Sekunde do kraja cooldown-a (0.0 ako nije u cooldown-u)."""
        with self._lock:
            return max(0.0, self._cooldown_until - time.time())

    # ── Bilježenje ───────────────────────────────────────────────────────────

    def record_request(self):
        """Bilježi novi zahtjev — povećava RPM i RPD brojač."""
        with self._lock:
            now = time.time()
            self._check_daily_reset()
            self._clean_rpm_window(now)
            self._rpm_window.append(now)
            self._rpd_count += 1

    def record_tokens(self, token_count: int):
        """Bilježi potrošene tokene u dnevnom TPD brojaču."""
        if token_count <= 0:
            return
        with self._lock:
            self._check_daily_reset()
            self._tpd_count += token_count

    def record_success(self, tokens: int = 0):
        """Bilježi uspješan odgovor (200 OK)."""
        if tokens > 0:
            self.record_tokens(tokens)

    def record_error(self, status_code: int, retry_after: Optional[float] = None):
        """
        Bilježi HTTP grešku i aktivira cooldown.

        Logika cooldown-a:
          • 429 RPM → cooldown iz Retry-After headera ili provider_profiles.cooldown_429_s
          • 429 RPD (dnevna kvota) → cooldown do slijedećeg reset sata
          • 401/403 → ključ se hladi 1h (pogrešan ključ, ne probaj odmah)
          • 5xx → kratki cooldown 30s (server problemi)
        """
        with self._lock:
            self._check_daily_reset()
            self.errors[status_code] = self.errors.get(status_code, 0) + 1

            if status_code == 429:
                self._daily_429_count += 1
                self._handle_429(retry_after)
            elif status_code in (401, 403):
                self._set_cooldown(3600.0, f"HTTP {status_code} — nevalidan ključ")
                syslog.warning(
                    "[quota] %s ...%s: HTTP %d — ključ na hlađenju 1h",
                    self.provider, self.key[-4:], status_code,
                )
                logger.warning(
                    "[quota] %s ...%s: HTTP %d — ključ na hlađenju 1h",
                    self.provider, self.key[-4:], status_code,
                )
            elif status_code >= 500:
                self._set_cooldown(30.0, f"HTTP {status_code} — server error")
                syslog.debug(
                    "[quota] %s ...%s: HTTP %d — kratki cooldown 30s",
                    self.provider, self.key[-4:], status_code,
                )

    def _handle_429(self, retry_after: Optional[float]):
        """Pod lock-om. Aktivira cooldown za 429 — RPM ili RPD."""
        try:
            from network.provider_profiles import get_cooldown_429
            default_cooldown = get_cooldown_429(self.provider)
        except ImportError:
            default_cooldown = 65.0

        # Pokušaj detectirati je li dnevna kvota iscrpljena
        # Heuristika: ako imamo 3+ 429 zaredom u ovom danu ili RPD >= rpd_safe
        rpd_exhausted = (self.rpd_safe > 0 and self._rpd_count >= self.rpd_safe)
        burst_exhausted = (self._daily_429_count >= 3)

        if rpd_exhausted or burst_exhausted:
            # Dnevna kvota — hladi se do slijedećeg reseta
            next_reset = _next_reset_timestamp(self._reset_hour)
            cooldown_s = max(0.0, next_reset - time.time())
            reason = "RPD dnevna kvota iscrpljena"
            syslog.warning(
                "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh (do reseta)",
                self.provider, self.key[-4:], cooldown_s / 3600,
            )
            logger.warning(
                "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh",
                self.provider, self.key[-4:], cooldown_s / 3600,
            )
        elif retry_after and retry_after > 0:
            # Server nam je rekao koliko da čekamo
            cooldown_s = float(retry_after) * 1.05  # +5% margine
            reason = f"RPM 429 (Retry-After: {retry_after:.0f}s)"
            syslog.info(
                "[quota] %s ...%s: RPM 429 — Retry-After=%.0fs → cooldown %.0fs",
                self.provider, self.key[-4:], retry_after, cooldown_s,
            )
            logger.info(
                "[quota] %s ...%s: RPM 429 — cooldown %.0fs (Retry-After)",
                self.provider, self.key[-4:], cooldown_s,
            )
        else:
            # Bez Retry-After — koristimo default iz profila
            cooldown_s = default_cooldown
            reason = f"RPM 429 (default cooldown {cooldown_s:.0f}s)"
            syslog.info(
                "[quota] %s ...%s: RPM 429 — default cooldown %.0fs",
                self.provider, self.key[-4:], cooldown_s,
            )
            logger.info(
                "[quota] %s ...%s: RPM 429 — cooldown %.0fs",
                self.provider, self.key[-4:], cooldown_s,
            )

        self._set_cooldown(cooldown_s, reason)

    def _set_cooldown(self, seconds: float, reason: str):
        """Pod lock-om. Postavlja cooldown timestamp."""
        new_until = time.time() + seconds
        if new_until > self._cooldown_until:  # ne skraćuj aktivni cooldown
            self._cooldown_until = new_until
            self._cooldown_reason = reason

    def set_cooldown_external(self, seconds: float, reason: str = "vanjski signal"):
        """API za rate_limiter.py — postavlja cooldown iz van (provider-level backoff)."""
        with self._lock:
            self._set_cooldown(seconds, reason)

    # ── Prikaz stanja ────────────────────────────────────────────────────────

    def to_status_dict(self) -> dict:
        """Snapshot trenutnog stanja — za UI i logiranje."""
        with self._lock:
            now = time.time()
            self._check_daily_reset()
            self._clean_rpm_window(now)
            cooldown_rem = max(0.0, self._cooldown_until - now)
            return {
                "key_masked":      self.key[:4] + "…" + self.key[-4:] if len(self.key) > 8 else "***",
                "provider":        self.provider,
                "rpm_current":     len(self._rpm_window),
                "rpm_safe":        self.rpm_safe,
                "rpd_current":     self._rpd_count,
                "rpd_safe":        self.rpd_safe,
                "tpd_current":     self._tpd_count,
                "cooldown_s":      round(cooldown_rem, 1),
                "cooldown_reason": self._cooldown_reason if cooldown_rem > 0 else "",
                "errors":          dict(self.errors),
                "daily_429":       self._daily_429_count,
            }


# ============================================================================
# ProviderQuota — agregat za sve ključeve jednog provajdera
# ============================================================================

class ProviderQuota:
    """
    Agregira informacije o svim ključevima jednog provajdera.
    Prati i provider-level cooldown (npr. IP ban).
    """

    def __init__(self, provider: str):
        self.provider = provider.upper()
        self._lock = threading.Lock()
        self._keys: dict[str, KeyQuota] = {}
        self._provider_cooldown_until: float = 0.0
        self._provider_cooldown_reason: str = ""

    def add_key(self, key: str, rpm_safe: int, rpd_safe: int) -> KeyQuota:
        with self._lock:
            if key not in self._keys:
                self._keys[key] = KeyQuota(key, self.provider, rpm_safe, rpd_safe)
                syslog.debug(
                    "[quota] %s: registrovan ključ ...%s (rpm_safe=%d, rpd_safe=%d)",
                    self.provider, key[-4:], rpm_safe, rpd_safe,
                )
            return self._keys[key]

    def get_key(self, key: str) -> Optional[KeyQuota]:
        with self._lock:
            return self._keys.get(key)

    def set_provider_cooldown(self, seconds: float, reason: str = "provider backoff"):
        """Provider-level cooldown — utječe na SVE ključeve tog provajdera."""
        with self._lock:
            new_until = time.time() + seconds
            if new_until > self._provider_cooldown_until:
                self._provider_cooldown_until = new_until
                self._provider_cooldown_reason = reason
                syslog.warning(
                    "[quota] %s: PROVIDER cooldown %.0fs — %s",
                    self.provider, seconds, reason,
                )
                logger.warning(
                    "[quota] %s: provider-level cooldown %.0fs (%s)",
                    self.provider, seconds, reason,
                )

    def provider_cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._provider_cooldown_until - time.time())

    def get_available_keys(self) -> list[tuple[str, KeyQuota]]:
        """Vraća listu (key_str, KeyQuota) za sve ključeve koji su trenutno dostupni."""
        provider_cd = self.provider_cooldown_remaining()
        if provider_cd > 0:
            syslog.debug(
                "[quota] %s: provider cooldown aktivan (%.0fs) — nema dostupnih ključeva",
                self.provider, provider_cd,
            )
            return []

        available = []
        with self._lock:
            for k, kq in self._keys.items():
                ok, _ = kq.is_available()
                if ok:
                    available.append((k, kq))
        return available

    def get_status_summary(self) -> dict:
        """Sažetak stanja za UI i logiranje."""
        provider_cd = self.provider_cooldown_remaining()
        with self._lock:
            keys_status = [kq.to_status_dict() for kq in self._keys.values()]
        available = sum(1 for s in keys_status
                        if s["cooldown_s"] == 0
                        and s["rpd_safe"] == 0 or s["rpd_current"] < s["rpd_safe"]
                        and s["rpm_current"] < s["rpm_safe"])
        return {
            "provider":                self.provider,
            "provider_cooldown_s":     round(provider_cd, 1),
            "provider_cooldown_reason": self._provider_cooldown_reason if provider_cd > 0 else "",
            "total_keys":              len(keys_status),
            "available_keys":          available,
            "keys":                    keys_status,
        }


# ============================================================================
# QuotaTracker — singleton koji upravlja svim provajderima
# ============================================================================

class QuotaTracker:
    """
    Singleton (po procesu). Centralno mjesto za praćenje svih kvota.
    Inicijalizira se iz FleetManager konfiguracije.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: dict[str, ProviderQuota] = {}
        syslog.info("[quota] QuotaTracker inicijaliziran")
        logger.info("[quota] QuotaTracker inicijaliziran")

    # ── Inicijalizacija ──────────────────────────────────────────────────────

    def register_key(self, provider: str, key: str, rpm_safe: int = 15, rpd_safe: int = 1000):
        """Registruje ključ u tracker. Poziva se iz FleetManager._load_config()."""
        prov = provider.upper()
        with self._lock:
            if prov not in self._providers:
                self._providers[prov] = ProviderQuota(prov)
        self._providers[prov].add_key(key, rpm_safe, rpd_safe)

    def initialize_from_fleet(self, fleet: dict):
        """
        Inicijalizira tracker iz FleetManager.fleet dict-a.
        fleet = {PROVIDER: [KeyState, ...], ...}
        """
        try:
            from network.provider_profiles import get_rpm_safe, get_rpd_safe
        except ImportError:
            def get_rpm_safe(p): return 15
            def get_rpd_safe(p): return 1000

        for provider, key_states in fleet.items():
            rpm_safe = get_rpm_safe(provider)
            rpd_safe = get_rpd_safe(provider)
            for ks in key_states:
                self.register_key(provider, ks.key, rpm_safe, rpd_safe)

        syslog.info(
            "[quota] Inicijalizacija iz flote: %d provajdera, %d ključeva ukupno",
            len(fleet),
            sum(len(v) for v in fleet.values()),
        )
        logger.info(
            "[quota] Inicijalizacija iz flote: %d provajdera, %d ključ(a)",
            len(fleet), sum(len(v) for v in fleet.values()),
        )

    # ── API za http_client.py ────────────────────────────────────────────────

    def record_request(self, provider: str, key: str):
        """Poziva se prije svakog API zahtjeva — povećava RPM/RPD brojač."""
        prov = provider.upper()
        pq = self._get_provider(prov)
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.record_request()
            syslog.debug(
                "[quota] %s ...%s: zahtjev (RPM=%d/%d, RPD=%d/%d)",
                prov, key[-4:],
                kq.current_rpm, kq.rpm_safe,
                kq.current_rpd, kq.rpd_safe,
            )

    def record_response(
        self,
        provider: str,
        key: str,
        status_code: int,
        tokens: int = 0,
        retry_after: Optional[float] = None,
        headers: Optional[dict] = None,
    ):
        """
        Poziva se nakon svakog API odgovora.
        Ažurira statistiku, tokene, greške i cooldown.
        """
        prov = provider.upper()
        pq = self._get_provider(prov)
        kq = pq.get_key(key) if pq else None
        if not kq:
            return

        # Pokušaj izvući Retry-After iz headera ako nije eksplicitno proslijeđen
        if retry_after is None and headers:
            ra_val = (
                headers.get("Retry-After")
                or headers.get("retry-after")
                or headers.get("x-ratelimit-reset-requests")
            )
            if ra_val:
                try:
                    retry_after = float(ra_val)
                except (TypeError, ValueError):
                    pass

        if status_code == 200:
            kq.record_success(tokens)
            if tokens > 0:
                syslog.debug(
                    "[quota] %s ...%s: OK 200, %d tokena (TPD=%d)",
                    prov, key[-4:], tokens, kq.current_tpd,
                )
        else:
            kq.record_error(status_code, retry_after)
            syslog.info(
                "[quota] %s ...%s: HTTP %d (retry_after=%s)",
                prov, key[-4:], status_code,
                f"{retry_after:.0f}s" if retry_after else "n/a",
            )

    def set_provider_cooldown(self, provider: str, seconds: float, reason: str = ""):
        """Provider-level cooldown (za IP ban ili globalni 429)."""
        prov = provider.upper()
        pq = self._get_provider(prov)
        if pq:
            pq.set_provider_cooldown(seconds, reason or "backoff")

    def set_key_cooldown(self, provider: str, key: str, seconds: float, reason: str = ""):
        """Ručno postavi cooldown za specifičan ključ."""
        prov = provider.upper()
        pq = self._get_provider(prov)
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.set_cooldown_external(seconds, reason or "vanjski signal")
            syslog.info(
                "[quota] %s ...%s: ručni cooldown %.0fs (%s)",
                prov, key[-4:], seconds, reason,
            )

    # ── API za rate_limiter.py / api_fleet.py ────────────────────────────────

    def is_key_available(self, provider: str, key: str) -> tuple[bool, str]:
        """
        Vraća (True, "") ako je ključ slobodan i u okviru kvote.
        Vraća (False, razlog) ako je na hlađenju ili iscrpio kvotu.
        """
        prov = provider.upper()
        pq = self._get_provider(prov)
        if not pq:
            return True, ""  # nema podataka = pretpostavi dostupno

        # Provider-level cooldown
        cd = pq.provider_cooldown_remaining()
        if cd > 0:
            return False, f"provider cooldown {cd:.0f}s"

        kq = pq.get_key(key)
        if not kq:
            return True, ""
        return kq.is_available()

    def get_available_keys_for_provider(self, provider: str) -> list[str]:
        """Lista ključeva koji su trenutno dostupni (bez cooldown-a, bez iscrpljene kvote)."""
        prov = provider.upper()
        pq = self._get_provider(prov)
        if not pq:
            return []
        return [k for k, _ in pq.get_available_keys()]

    # ── Status i UI ──────────────────────────────────────────────────────────

    def get_provider_status(self, provider: str) -> Optional[dict]:
        prov = provider.upper()
        pq = self._get_provider(prov)
        return pq.get_status_summary() if pq else None

    def get_all_status(self) -> dict:
        """Snapshot stanja svih provajdera i ključeva."""
        with self._lock:
            providers = list(self._providers.keys())
        return {prov: self._providers[prov].get_status_summary() for prov in providers}

    def log_status_summary(self):
        """Ispiše sažetak stanja svih ključeva u log."""
        all_status = self.get_all_status()
        lines = ["[quota] === STATUS KVOTA ==="]
        for prov, status in sorted(all_status.items()):
            cd = status["provider_cooldown_s"]
            cd_str = f" [PROVIDER COOLDOWN {cd:.0f}s]" if cd > 0 else ""
            lines.append(
                f"  {prov:<14} {status['available_keys']}/{status['total_keys']} dostupno{cd_str}"
            )
            for ks in status["keys"]:
                kcd = ks["cooldown_s"]
                kcd_str = f" ❄ {kcd:.0f}s" if kcd > 0 else ""
                err_str = " ERR:" + str(ks["errors"]) if ks["errors"] else ""
                lines.append(
                    f"    {ks['key_masked']} RPM={ks['rpm_current']}/{ks['rpm_safe']}"
                    f" RPD={ks['rpd_current']}/{ks['rpd_safe'] or '∞'}"
                    f" TPD={ks['tpd_current']}{kcd_str}{err_str}"
                )
        summary = "\n".join(lines)
        syslog.info(summary)
        logger.info(summary)

    # ── Interno ──────────────────────────────────────────────────────────────

    def _get_provider(self, prov: str) -> Optional[ProviderQuota]:
        with self._lock:
            return self._providers.get(prov)


# ── Singleton instanca ────────────────────────────────────────────────────────
quota_tracker = QuotaTracker()
