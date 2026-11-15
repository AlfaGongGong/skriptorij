"""network/quota_tracker.py  (L33: dnevna kvota po ključu i modelu)

Per-ključ cooldown praćenje. Prati RPM/RPD iscrpljenost i cooldown stanje
svakog API ključa. Podaci se persistiraju na disk kako bi preživjeli restart.
"""

import contextlib
import datetime as _dt
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_cooldown_429_s(provider: str) -> float:
    try:
        from config.ai_config import get_cooldown_429

        return get_cooldown_429(provider)
    except Exception:
        return 15.0


# L33: dnevna kvota po KLJUČU i MODELU (Google limiti su po projektu i po modelu).
_DNEVNI_RX = re.compile(r"per[_ ]?day|\bdaily\b|\brpd\b", re.I)
_MODEL_URL_RX = re.compile(r"/models/([^:/?]+)")


def _pacific(now: float):
    try:
        from zoneinfo import ZoneInfo

        return _dt.datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
    except Exception:
        return _dt.datetime.fromtimestamp(now, _dt.timezone(_dt.timedelta(hours=-8)))


def dan_kvote(now: float | None = None) -> str:
    """Datum (Pacific) po kojem Google broji dnevnu kvotu; mijenja se u ponoć Pacific."""
    return _pacific(time.time() if now is None else now).strftime("%Y-%m-%d")


def sekundi_do_reseta(now: float | None = None) -> float:
    """Sekunde do sljedeceg dnevnog reseta (ponoć Pacific) + 60 s rezerve."""
    now = time.time() if now is None else now
    p = _pacific(now)
    sutra = _dt.datetime.combine(
        p.date() + _dt.timedelta(days=1), _dt.time(0, 0), tzinfo=p.tzinfo
    )
    return max(60.0, sutra.timestamp() - now + 60.0)


def je_dnevni_limit(body) -> bool:
    """True ako 429 odgovor govori o DNEVNOM limitu (PerDay / daily / RPD)."""
    try:
        s = body if isinstance(body, str) else json.dumps(body, default=str)
    except Exception:
        return False
    return bool(_DNEVNI_RX.search(s or ""))


def model_iz_url(url: str) -> str:
    m = _MODEL_URL_RX.search(url or "")
    return m.group(1) if m else ""


def _fmt_trajanje(s: float) -> str:
    s = int(max(0, s))
    h, r = divmod(s, 3600)
    return ("%dh %02dmin" % (h, r // 60)) if h else ("%dmin" % max(1, r // 60))


def _lok_vrijeme(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%d.%m. %H:%M")


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
        self.tpm_safe: float = 0.0  # FIX tpm-gate: 0 = iskljuceno
        self._tpm_window: list = []  # FIX tpm-gate: [(ts, tokens)] zadnjih 60s
        self.rpm_safe: float = 0.0  # FIX fleet-status
        self.rpd_safe: float = 0.0  # FIX fleet-status
        self._rpm_window: list = []  # FIX fleet-status: [ts, ...] zadnjih 60s
        self._rpd_window: list = []  # FIX fleet-status: [ts, ...] zadnjih 24h
        self._tpd_window: list = []  # FIX fleet-status: [(ts, tokens)] zadnjih 24h
        self._consecutive_401: int = 0
        self._model_cd: dict = {}  # L33: model -> (until, reason)
        self._model_rpd: dict = {}  # L33: model -> {'dan': 'YYYY-MM-DD', 'n': int}

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
            if self.tpm_safe > 0:
                cutoff = now - 60.0
                self._tpm_window = [
                    (t, tok) for t, tok in self._tpm_window if t >= cutoff
                ]
                used = sum(tok for _, tok in self._tpm_window)
                if used >= self.tpm_safe:
                    # FIX #5: čekaj dok dovoljno tokena ne istekne iz prozora,
                    # ne samo najstariji. Iteriraj sortirano po vremenu.
                    sorted_window = sorted(self._tpm_window, key=lambda x: x[0])
                    needed = used - self.tpm_safe + 1  # koliko tokena mora izaći
                    freed = 0
                    wait_until = now
                    for t, tok in sorted_window:
                        freed += tok
                        wait_until = t + 60.0
                        if freed >= needed:
                            break
                    wait = max(0.0, wait_until - now)
                    return (
                        False,
                        f"tpm_gate cekaj {wait:.0f}s ({used:.0f}/{self.tpm_safe:.0f} tok u zadnjih 60 sekundi)",
                    )
            return True, ""

    def record_request(self):
        with self._lock:
            now = time.time()
            self._last_request_time = now
            self._rpm_window.append(now)
            self._rpd_window.append(now)
            self._rpm_window = [t for t in self._rpm_window if now - t < 60.0]
            self._rpd_window = [t for t in self._rpd_window if now - t < 86400.0]

    def record_success(self, tokens: int = 0):
        with self._lock:
            if tokens > 0:
                now = time.time()
                self._tpm_window.append((now, tokens))
                cutoff = now - 60.0
                self._tpm_window = [
                    (t, tok) for t, tok in self._tpm_window if t >= cutoff
                ]
                self._tpd_window.append((now, tokens))
                self._tpd_window = [
                    (t, tok) for t, tok in self._tpd_window if now - t < 86400.0
                ]

    def record_error(self, status_code: int, retry_after: float | None = None):
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
                        self.provider,
                        self.key[-4:],
                        status_code,
                        self._consecutive_401,
                    )
                else:
                    self._set_cooldown(
                        300.0,
                        f"401 privremeni cooldown (pokušaj {self._consecutive_401}/2)",
                    )
                    logger.warning(
                        "[QuotaTracker] %s ...%s → %d — kratki cooldown 5min (pokušaj %d/2)",
                        self.provider,
                        self.key[-4:],
                        status_code,
                        self._consecutive_401,
                    )

            elif status_code == 503:
                # FIX 2026-09-26: 503 je server-side — samo provider-level cooldown
                try:
                    from network.quota_tracker import quota_tracker as _qt

                    _qt.set_provider_cooldown(self.provider, 10.0, "503 server")
                except Exception:
                    logger.exception("[C1_http] quota_tracker.py:141 Exception")
                logger.warning(
                    "[QuotaTracker] %s ...%s → 503 (server) — provider cooldown 10s",
                    self.provider,
                    self.key[-4:],
                )

            elif status_code == 429:
                if retry_after and retry_after > 3600:
                    cooldown_s = min(float(retry_after), 90000.0)
                    reason = "RPD kvota (dnevni limit)"
                    logger.warning(
                        "[QuotaTracker] %s ...%s → RPD EXHAUSTED — cooldown %.0fs (%.1fh)",
                        self.provider,
                        self.key[-4:],
                        cooldown_s,
                        cooldown_s / 3600,
                    )
                elif retry_after and retry_after > 60:
                    cooldown_s = min(float(retry_after), 86400.0)
                    reason = "429 dugi cooldown"
                    logger.warning(
                        "[QuotaTracker] %s ...%s → 429 dugi cooldown %.0fs",
                        self.provider,
                        self.key[-4:],
                        cooldown_s,
                    )
                elif retry_after and retry_after > 0:
                    cooldown_s = min(float(retry_after), 120.0)
                    reason = "RPM 429 (Retry-After)"
                else:
                    cooldown_s = _get_cooldown_429_s(self.provider)
                    reason = f"RPM 429 (profil {cooldown_s:.0f}s)"
                    logger.info(
                        "[QuotaTracker] %s ...%s → 429 bez Retry-After — cooldown: %.0fs",
                        self.provider,
                        self.key[-4:],
                        cooldown_s,
                    )
                self._set_cooldown(cooldown_s, reason)

    # ---- L33: stanje po modelu ----
    def set_model_cooldown(self, model: str, seconds: float, reason: str = ""):
        with self._lock:
            until = time.time() + seconds
            cur = self._model_cd.get(model)
            if not cur or until > cur[0]:
                self._model_cd[model] = (until, reason)

    def model_cooldown(self, model: str) -> tuple:
        with self._lock:
            cur = self._model_cd.get(model)
            now = time.time()
            if cur and cur[0] > now:
                return cur[0] - now, cur[1]
            if cur:
                del self._model_cd[model]
            return 0.0, ""

    def record_model_request(self, model: str) -> int:
        with self._lock:
            dan = dan_kvote()
            e = self._model_rpd.get(model)
            if not e or e.get("dan") != dan:
                e = {"dan": dan, "n": 0}
            e["n"] += 1
            self._model_rpd[model] = e
            return e["n"]

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
        with self._lock:
            now = time.time()
            self._rpm_window = [t for t in self._rpm_window if now - t < 60.0]
            return len(self._rpm_window)

    @property
    def current_rpd(self) -> int:
        with self._lock:
            now = time.time()
            self._rpd_window = [t for t in self._rpd_window if now - t < 86400.0]
            return len(self._rpd_window)

    @property
    def current_tpd(self) -> int:
        with self._lock:
            now = time.time()
            self._tpd_window = [
                (t, tok) for t, tok in self._tpd_window if now - t < 86400.0
            ]
            return sum(tok for _, tok in self._tpd_window)

    def to_status_dict(self) -> dict:
        with self._lock:
            now = time.time()
            cd = max(0.0, self._cooldown_until - now)
            self._rpm_window = [t for t in self._rpm_window if now - t < 60.0]
            self._rpd_window = [t for t in self._rpd_window if now - t < 86400.0]
            self._tpd_window = [
                (t, tok) for t, tok in self._tpd_window if now - t < 86400.0
            ]
            return {
                "key_masked": self.key[-4:] if len(self.key) > 4 else "***",
                "provider": self.provider,
                "rpm_current": len(self._rpm_window),
                "rpm_safe": self.rpm_safe,
                "rpd_current": len(self._rpd_window),
                "rpd_safe": self.rpd_safe,
                "tpd_current": sum(tok for _, tok in self._tpd_window),
                "cooldown_s": round(cd, 1),
                "cooldown_reason": self._cooldown_reason if cd > 0 else "",
                "errors": dict(self.errors),
                "model_cooldowns": {
                    m: round(u - now, 1) for m, (u, _r) in self._model_cd.items() if u > now
                },
            }


class ProviderQuota:
    def __init__(self, provider: str):
        self.provider = provider.upper()
        self._lock = threading.Lock()
        self._keys: dict[str, KeyQuota] = {}
        # BUG #4 fix: provider-level cooldown stanje
        self._provider_cooldown_until: float = 0.0
        self._provider_cooldown_reason: str = ""

    def add_key(
        self,
        key: str,
        rpm_safe: int = 0,
        rpd_safe: int = 0,
        min_gap_s: float = 2.0,
        tpm_safe: float = 0.0,
    ) -> KeyQuota:
        with self._lock:
            if key not in self._keys:
                kq = KeyQuota(key, self.provider)
                kq.min_gap_s = min_gap_s
                kq.tpm_safe = tpm_safe
                kq.rpm_safe = rpm_safe
                kq.rpd_safe = rpd_safe
                self._keys[key] = kq
            return self._keys[key]

    def get_key(self, key: str) -> KeyQuota | None:
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
    _ispisano = False  # L33: ispis stanja jednom po procesu
    _plock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: dict[str, ProviderQuota] = {}

    def register_key(
        self,
        provider: str,
        key: str,
        rpm_safe: int = 15,
        rpd_safe: int = 1000,
        min_gap_s: float = 2.0,
        tpm_safe: float = 0.0,
    ):
        prov = provider.upper()
        with self._lock:
            if prov not in self._providers:
                self._providers[prov] = ProviderQuota(prov)
        self._providers[prov].add_key(key, rpm_safe, rpd_safe, min_gap_s, tpm_safe)

    def initialize_from_fleet(self, fleet: dict):
        try:
            from config.ai_config import get_min_gap as _get_min_gap
        except ImportError:
            _get_min_gap = lambda p: 2.0  # noqa: E731
        try:
            from config.ai_config import get_tpm_safe as _get_tpm_safe
        except ImportError:
            _get_tpm_safe = lambda p: 0.0  # noqa: E731
        try:
            from config.ai_config import get_rpd_safe as _get_rpd_safe
            from config.ai_config import get_rpm_safe as _get_rpm_safe
        except ImportError:
            _get_rpm_safe = lambda p: 0
            _get_rpd_safe = lambda p: 0

        for provider, key_states in fleet.items():
            prov_u = provider.upper()
            gap = _get_min_gap(prov_u)
            tpm = _get_tpm_safe(prov_u)
            rpm_s = _get_rpm_safe(prov_u)
            rpd_s = _get_rpd_safe(prov_u)
            for ks in key_states:
                self.register_key(
                    prov_u,
                    ks.key,
                    rpm_safe=rpm_s,
                    rpd_safe=rpd_s,
                    min_gap_s=gap,
                    tpm_safe=tpm,
                )
                if prov_u == "GEMINI":
                    gemma_gap = _get_min_gap("GEMMA")
                    gemma_tpm = _get_tpm_safe("GEMMA")
                    gemma_rpm = _get_rpm_safe("GEMMA")
                    gemma_rpd = _get_rpd_safe("GEMMA")
                    self.register_key(
                        "GEMMA",
                        ks.key,
                        rpm_safe=gemma_rpm,
                        rpd_safe=gemma_rpd,
                        min_gap_s=gemma_gap,
                        tpm_safe=gemma_tpm,
                    )
        logger.info("QuotaTracker inicijaliziran: %d provajdera", len(fleet))
        self._restore_cooldowns()
        if not QuotaTracker._ispisano:
            QuotaTracker._ispisano = True
            try:
                for _l in self.ispis_stanja():
                    print(_l, flush=True)
                    logger.info(_l)
            except Exception as e:
                logger.warning("[QuotaTracker] ispis stanja nije uspio: %s", e)

    def _restore_cooldowns(self):
        """L33: obnavlja cooldown (ključ i model), prozore i dnevne brojače modela s diska.
        Istekli cooldowni i brojači iz prošlog dana se odbacuju (= reset)."""
        self._restored_info = {"cooldown": 0, "model": 0, "istekli": []}
        info = self._restored_info
        try:
            if not os.path.exists(self._PERSIST_PATH):
                return
            with open(self._PERSIST_PATH, encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            danas = dan_kvote(now)
            for prov, keys in data.items():
                pq = self._get_provider(prov)
                if not pq:
                    continue
                for key, ent in keys.items():
                    kq = pq.get_key(key)
                    if not kq:
                        continue
                    oznaka = "%s ...%s" % (prov, key[-4:])
                    until = ent.get("cooldown_until", 0)
                    if until > now:
                        kq.set_cooldown_external(until - now, ent.get("cooldown_reason", ""))
                        info["cooldown"] += 1
                    elif until:
                        info["istekli"].append("%s (ključ)" % oznaka)
                    with kq._lock:
                        if not kq._rpm_window:
                            kq._rpm_window = [t for t in ent.get("rpm_window", []) if now - t < 60.0]
                        if not kq._rpd_window:
                            kq._rpd_window = [t for t in ent.get("rpd_window", []) if now - t < 86400.0]
                        if not kq._tpd_window:
                            kq._tpd_window = [
                                (t, tok) for t, tok in ent.get("tpd_window", []) if now - t < 86400.0
                            ]
                    for m, mi in (ent.get("model_cooldowns") or {}).items():
                        u = mi.get("until", 0)
                        if u > now:
                            kq.set_model_cooldown(m, u - now, mi.get("reason", ""))
                            info["model"] += 1
                        else:
                            info["istekli"].append("%s %s" % (oznaka, m))
                    for m, e in (ent.get("model_rpd") or {}).items():
                        if e.get("dan") == danas:
                            with kq._lock:
                                cur = kq._model_rpd.get(m)
                                n = int(e.get("n", 0))
                                if not cur or cur.get("dan") != danas or cur.get("n", 0) < n:
                                    kq._model_rpd[m] = {"dan": danas, "n": n}
            if info["cooldown"] or info["model"]:
                logger.info(
                    "[QuotaTracker] Obnovljeno s diska: %d ključ(a), %d model(a) u cooldownu",
                    info["cooldown"],
                    info["model"],
                )
        except Exception as e:
            logger.warning("[QuotaTracker] Nije moguće obnoviti cooldown stanje: %s", e)

    def _persist_cooldowns(self):
        # NAPOMENA: ne uzimati kq._lock (poziva se i iz record_error pod tim lockom).
        now = time.time()
        danas = dan_kvote(now)
        data = {}
        with self._lock:
            provs = list(self._providers.items())
        for prov, pq in provs:
            with pq._lock:
                keys = list(pq._keys.items())
            for key, kq in keys:
                ent = {"cooldown_until": 0, "cooldown_reason": ""}
                dirty = False
                until = kq._cooldown_until
                if until > now:
                    ent["cooldown_until"] = until
                    ent["cooldown_reason"] = kq._cooldown_reason
                    dirty = True
                _rpm = [t for t in list(kq._rpm_window) if now - t < 60.0]
                _rpd = [t for t in list(kq._rpd_window) if now - t < 86400.0]
                _tpd = [(t, tok) for t, tok in list(kq._tpd_window) if now - t < 86400.0]
                if _rpm or _rpd or _tpd:
                    ent["rpm_window"], ent["rpd_window"], ent["tpd_window"] = _rpm, _rpd, _tpd
                    dirty = True
                mcd = {
                    m: {"until": u, "reason": r}
                    for m, (u, r) in list(kq._model_cd.items())
                    if u > now
                }
                if mcd:
                    ent["model_cooldowns"] = mcd
                    dirty = True
                mrpd = {m: dict(e) for m, e in list(kq._model_rpd.items()) if e.get("dan") == danas}
                if mrpd:
                    ent["model_rpd"] = mrpd
                    dirty = True
                if dirty:
                    data.setdefault(prov, {})[key] = ent
        try:
            with self._plock:
                tmp = self._PERSIST_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, self._PERSIST_PATH)
        except Exception as e:
            logger.warning("[QuotaTracker] Nije moguće snimiti cooldown stanje: %s", e)

    # ---- L33: po modelu ----
    def is_model_available(self, provider: str, key: str, model: str) -> tuple:
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if not kq or not model:
            return True, ""
        rem, reason = kq.model_cooldown(model)
        if rem > 0:
            return False, "model %s cooldown %.0fs (%s)" % (model, rem, reason)
        return True, ""

    def set_model_cooldown(self, provider: str, key: str, model: str, seconds: float, reason: str = ""):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq and model:
            kq.set_model_cooldown(model, seconds, reason)
            self._persist_cooldowns()

    def record_model_request(self, provider: str, key: str, model: str):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq and model:
            n = kq.record_model_request(model)
            if n % 5 == 1:
                self._persist_cooldowns()

    def obradi_429_model(self, provider: str, key: str, model: str, body) -> bool:
        """429 s dnevnim limitom za JEDAN model: cooldown samo tog modela do sljedeceg
        reseta (ponoć Pacific). Vraća True ako je obrađeno (ključ NE ide u cooldown)."""
        if not model or not je_dnevni_limit(body):
            return False
        sek = sekundi_do_reseta()
        self.set_model_cooldown(provider, key, model, sek, "dnevni limit modela")
        logger.warning(
            "[QuotaTracker] %s ...%s model %s: dnevni limit — model na cooldown %.1fh (ključ ostaje dostupan za druge modele)",
            provider,
            key[-4:],
            model,
            sek / 3600,
        )
        return True

    def ispis_stanja(self) -> list:
        """Čitljiv ispis: što je iscrpljeno, do kada, koliko poziva po modelu danas."""
        now = time.time()
        danas = dan_kvote(now)
        sek = sekundi_do_reseta(now)
        redovi = [
            "[Kvote] dnevni limiti Google modela resetiraju se u %s (za %s)"
            % (_lok_vrijeme(now + sek), _fmt_trajanje(sek))
        ]
        with self._lock:
            provs = list(self._providers.items())
        n_red = 0
        for prov, pq in sorted(provs):
            with pq._lock:
                keys = list(pq._keys.items())
            for key, kq in keys:
                dijelovi = []
                rem = kq.cooldown_remaining()
                if rem > 0:
                    dijelovi.append(
                        "ključ na cooldownu još %s (%s)" % (_fmt_trajanje(rem), kq._cooldown_reason)
                    )
                for m, (u, r) in sorted(list(kq._model_cd.items())):
                    if u > now:
                        dijelovi.append(
                            "model %s ISCRPLJEN do %s (za %s)" % (m, _lok_vrijeme(u), _fmt_trajanje(u - now))
                        )
                for m, e in sorted(list(kq._model_rpd.items())):
                    if e.get("dan") == danas and e.get("n", 0) > 0:
                        dijelovi.append("%s: %d poziva danas" % (m, e["n"]))
                if dijelovi:
                    redovi.append("  %s ...%s: %s" % (prov, key[-4:], "; ".join(dijelovi)))
                    n_red += 1
        if n_red == 0:
            redovi.append("[Kvote] nijedan ključ ni model trenutno nije iscrpljen")
        info = getattr(self, "_restored_info", None) or {}
        if info.get("istekli"):
            redovi.append(
                "[Kvote] resetirano od zadnjeg pokretanja (limit istekao): " + ", ".join(info["istekli"][:10])
            )
        return redovi

    def record_request(self, provider: str, key: str):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.record_request()

    def record_response(
        self,
        provider: str,
        key: str,
        status_code: int,
        tokens: int = 0,
        retry_after=None,
        headers=None,
        model=None,
        model_limit=False,
    ):
        # BUG #7 fix: jedan lookup umjesto dva — thread-safer, bez duplog _get_provider
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if not kq:
            return
        if model_limit:
            # L33: dnevni limit samo jednog modela — ključ ostaje dostupan
            with kq._lock:
                kq.errors[429] = kq.errors.get(429, 0) + 1
            self._persist_cooldowns()
            return
        if status_code == 200:
            with kq._lock:
                kq._consecutive_401 = 0
            kq.record_success(tokens)
        elif status_code >= 400:
            if retry_after is None and headers:
                ra = headers.get("Retry-After") or headers.get("retry-after")
                if ra:
                    with contextlib.suppress(TypeError, ValueError):
                        retry_after = float(ra)
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

    def set_key_cooldown(
        self, provider: str, key: str, seconds: float, reason: str = ""
    ):
        pq = self._get_provider(provider.upper())
        kq = pq.get_key(key) if pq else None
        if kq:
            kq.set_cooldown_external(seconds, reason)
            self._persist_cooldowns()

    def get_provider_status(self, provider: str) -> dict | None:
        pq = self._get_provider(provider.upper())
        return pq.get_status_summary() if pq else None

    def _load_windows_for_key(self, kq):
        """2026-10-24 B3: uciti RPM/RPD/TPD windows iz quota_cooldowns.json (ako postoje)."""
        try:
            if not self._PERSIST_PATH.exists():
                return
            with open(self._PERSIST_PATH, encoding="utf-8") as f:
                data = json.load(f)
            prov = kq.provider
            if prov not in data:
                return
            if kq.key not in data[prov]:
                return
            entry = data[prov][kq.key]
            now = time.time()
            if "rpm_window" in entry:
                kq._rpm_window = [t for t in entry["rpm_window"] if now - t < 60.0]
            if "rpd_window" in entry:
                kq._rpd_window = [t for t in entry["rpd_window"] if now - t < 86400.0]
            if "tpd_window" in entry:
                kq._tpd_window = [
                    (t, tok) for t, tok in entry["tpd_window"] if now - t < 86400.0
                ]
        except Exception as e:
            logger.debug("[QuotaTracker] Ucitavanje windows-a palo: %s", e)

    def dnevna_kvota_iscrpljena(self, min_s: float = 3600.0) -> tuple:
        """L30: (True, sekundi do najranijeg ključa) ako SVI ključevi SVIH providera
        imaju cooldown dulji od min_s (dnevni RPD limit); inače (False, 0.0)."""
        with self._lock:
            provs = list(self._providers.values())
        n_keys = 0
        min_rem = None
        for pq in provs:
            with pq._lock:
                kqs = list(pq._keys.values())
            for kq in kqs:
                n_keys += 1
                rem = kq.cooldown_remaining()
                if rem <= min_s:
                    return False, 0.0
                min_rem = rem if min_rem is None else min(min_rem, rem)
        if n_keys == 0:
            return False, 0.0
        return True, float(min_rem or 0.0)

    def _get_provider(self, prov: str) -> ProviderQuota | None:
        with self._lock:
            return self._providers.get(prov)


quota_tracker = QuotaTracker()