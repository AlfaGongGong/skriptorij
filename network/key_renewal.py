"""network/key_renewal.py

Smart reset mehanizam koji simulira obnovu ključa od strane provajdera.

Logika po tipu obnove:
──────────────────────────────────────────────────────────────────────
RPM_RESET   → Ključ je prekoračio minutni limit (429 kratki).
              Resetuje: cooldown, _last_request_time, rate_limiter per-key.
              NE resetuje: calls_ok/failed/rejected, 401 historiju.

RPD_RESET   → Provajder je resetovao dnevnu kvotu (ponoć UTC ili ručno).
              Resetuje: cooldown, errors, consecutive_401,
              rate_limiter provider backoff za cijeli provajder.
              NE resetuje: calls_ok (historija uspješnih poziva ostaje).

FULL_RESET  → Ključ regenerisan ili operatorski reset.
              Resetuje: SVE — cooldown, errors, consecutive_401,
              last_request_time, calls_ok/failed/rejected, rate_limiter.

UNBAN       → Ključ bio blacklistiran (401×2 ili 402), provajder reaktivirao.
              Resetuje: cooldown, consecutive_401, errors[401/402/403].
              NE resetuje: calls_ok/failed (historija ostaje), RPD brojač.
"""

import logging
import threading
from typing import Literal

logger = logging.getLogger(__name__)

RenewalMode = Literal["rpm_reset", "rpd_reset", "full_reset", "unban"]

_RENEWAL_LOCK = threading.Lock()


def _reset_kq_cooldown(kq) -> None:
    with kq._lock:
        kq._cooldown_until = 0.0
        kq._cooldown_reason = ""


def _reset_kq_last_request(kq) -> None:
    with kq._lock:
        kq._last_request_time = 0.0


def _reset_kq_consecutive_401(kq) -> None:
    with kq._lock:
        kq._consecutive_401 = 0


def _reset_kq_errors(kq, codes: list | None = None) -> None:
    with kq._lock:
        if codes is None:
            kq.errors.clear()
        else:
            for c in codes:
                kq.errors.pop(c, None)


def _reset_ks_counters(ks) -> None:
    ks.calls_ok = 0
    ks.calls_failed = 0
    ks.calls_rejected = {}


def _reset_rate_limiter_provider(provider: str) -> None:
    try:
        from network.rate_limiter import _PROVIDER_COOLDOWN_UNTIL
        _PROVIDER_COOLDOWN_UNTIL.pop(provider.upper(), None)
    except Exception as e:
        logger.debug("[key_renewal] rate_limiter provider reset preskočen: %s", e)


def _reset_rate_limiter_key(provider: str, key: str) -> None:
    try:
        from network.rate_limiter import _LAST_CALLS_KEY, _LAST_CALLS_KEY_LOCK
        with _LAST_CALLS_KEY_LOCK:
            _LAST_CALLS_KEY.pop((provider.upper(), key), None)
    except Exception as e:
        logger.debug("[key_renewal] rate_limiter key reset preskočen: %s", e)


def renew_key(provider: str, key: str, mode: RenewalMode) -> dict:
    """
    Resetuje stanje ključa prema odabranom modu obnove.
    Thread-safe. Persistuje promjene na disk.

    Vraća: { ok, provider, key_masked, mode, actions, error }
    """
    prov = provider.upper()
    key_masked = f"...{key[-6:]}" if len(key) > 6 else "***"
    actions: list[str] = []

    with _RENEWAL_LOCK:
        try:
            from network.quota_tracker import quota_tracker
            from api_fleet import get_active_fleet

            pq = quota_tracker._get_provider(prov)
            kq = pq.get_key(key) if pq else None
            if kq is None:
                logger.warning(
                    "[key_renewal] %s %s: KeyQuota ne postoji — nastavlja s FleetManager resetom",
                    prov, key_masked,
                )

            fm = get_active_fleet()
            ks = None
            ks_gemma = None
            if fm is not None:
                with fm.lock:
                    ks = fm._find_key(prov, key)
                    ks_gemma = fm._find_key("GEMMA", key) if prov == "GEMINI" else None

            if kq is None and ks is None:
                return {
                    "ok": False, "provider": prov, "key_masked": key_masked,
                    "mode": mode, "actions": [],
                    "error": f"Ključ {key_masked} nije pronađen ni u quota_tracker-u ni u floti",
                }

            if mode == "rpm_reset":
                if kq:
                    _reset_kq_cooldown(kq)
                    _reset_kq_last_request(kq)
                    actions.append("kq.cooldown + last_request → 0")
                _reset_rate_limiter_key(prov, key)
                actions.append("rate_limiter key entry obrisan")
                if prov == "GEMINI":
                    pq_g = quota_tracker._get_provider("GEMMA")
                    kq_g = pq_g.get_key(key) if pq_g else None
                    if kq_g:
                        _reset_kq_cooldown(kq_g)
                        _reset_kq_last_request(kq_g)
                        actions.append("GEMMA kq.cooldown + last_request → 0")
                    _reset_rate_limiter_key("GEMMA", key)

            elif mode == "rpd_reset":
                if kq:
                    _reset_kq_cooldown(kq)
                    _reset_kq_last_request(kq)
                    _reset_kq_errors(kq)
                    _reset_kq_consecutive_401(kq)
                    actions.append("kq: cooldown + last_request + errors + consecutive_401 → 0")
                _reset_rate_limiter_provider(prov)
                _reset_rate_limiter_key(prov, key)
                actions.append(f"rate_limiter: provider backoff + key entry obrisan ({prov})")
                if prov == "GEMINI":
                    pq_g = quota_tracker._get_provider("GEMMA")
                    kq_g = pq_g.get_key(key) if pq_g else None
                    if kq_g:
                        _reset_kq_cooldown(kq_g)
                        _reset_kq_errors(kq_g)
                        _reset_kq_consecutive_401(kq_g)
                        _reset_kq_last_request(kq_g)
                        actions.append("GEMMA kq potpuno resetovan")
                    _reset_rate_limiter_provider("GEMMA")
                    _reset_rate_limiter_key("GEMMA", key)

            elif mode == "full_reset":
                if kq:
                    _reset_kq_cooldown(kq)
                    _reset_kq_last_request(kq)
                    _reset_kq_errors(kq)
                    _reset_kq_consecutive_401(kq)
                    actions.append("kq: cooldown + last_request + errors + consecutive_401 → 0")
                if ks:
                    with fm.lock:
                        _reset_ks_counters(ks)
                    actions.append("ks: calls_ok/failed/rejected → 0")
                if ks_gemma:
                    with fm.lock:
                        _reset_ks_counters(ks_gemma)
                    actions.append("GEMMA ks: calls_ok/failed/rejected → 0")
                _reset_rate_limiter_provider(prov)
                _reset_rate_limiter_key(prov, key)
                actions.append(f"rate_limiter: provider backoff + key entry obrisan ({prov})")
                if prov == "GEMINI":
                    pq_g = quota_tracker._get_provider("GEMMA")
                    kq_g = pq_g.get_key(key) if pq_g else None
                    if kq_g:
                        _reset_kq_cooldown(kq_g)
                        _reset_kq_last_request(kq_g)
                        _reset_kq_errors(kq_g)
                        _reset_kq_consecutive_401(kq_g)
                        actions.append("GEMMA kq potpuno resetovan")
                    _reset_rate_limiter_provider("GEMMA")
                    _reset_rate_limiter_key("GEMMA", key)

            elif mode == "unban":
                if kq:
                    _reset_kq_cooldown(kq)
                    _reset_kq_consecutive_401(kq)
                    _reset_kq_errors(kq, codes=[401, 402, 403])
                    actions.append("kq: cooldown + consecutive_401 + errors[401/402/403] → 0")
                _reset_rate_limiter_key(prov, key)
                actions.append("rate_limiter key entry obrisan")
                if prov == "GEMINI":
                    pq_g = quota_tracker._get_provider("GEMMA")
                    kq_g = pq_g.get_key(key) if pq_g else None
                    if kq_g:
                        _reset_kq_cooldown(kq_g)
                        _reset_kq_consecutive_401(kq_g)
                        _reset_kq_errors(kq_g, codes=[401, 402, 403])
                        actions.append("GEMMA kq: unban resetovan")
                    _reset_rate_limiter_key("GEMMA", key)

            else:
                return {
                    "ok": False, "provider": prov, "key_masked": key_masked,
                    "mode": mode, "actions": [],
                    "error": f"Nepoznat mode: '{mode}'. Dozvoljeni: rpm_reset, rpd_reset, full_reset, unban",
                }

            quota_tracker._persist_cooldowns()
            actions.append("quota_cooldowns.json ažuriran")
            if fm is not None:
                fm._save_state()
                actions.append("api_state.json ažuriran")

            logger.info("[key_renewal] %s %s — mode=%s — %s", prov, key_masked, mode, "; ".join(actions))
            return {"ok": True, "provider": prov, "key_masked": key_masked, "mode": mode, "actions": actions, "error": None}

        except Exception as exc:
            logger.exception("[key_renewal] Greška pri obnovi ključa %s %s", prov, key_masked)
            return {"ok": False, "provider": prov, "key_masked": key_masked, "mode": mode, "actions": actions, "error": str(exc)}


def renew_provider(provider: str, mode: RenewalMode) -> dict:
    """Resetuje SVE ključeve jednog provajdera (batch operacija)."""
    prov = provider.upper()
    results = []
    errors = []
    try:
        from api_fleet import get_active_fleet
        fm = get_active_fleet()
        if fm is None:
            return {"ok": False, "provider": prov, "error": "FleetManager nije inicijaliziran", "results": []}
        with fm.lock:
            keys_in_fleet = [ks.key for ks in fm.fleet.get(prov, [])]
        if not keys_in_fleet:
            return {"ok": False, "provider": prov, "error": f"Nema ključeva za {prov}", "results": []}
        for key in keys_in_fleet:
            r = renew_key(prov, key, mode)
            results.append(r)
            if not r["ok"]:
                errors.append(r.get("error", "?"))
        if mode in ("rpd_reset", "full_reset"):
            _reset_rate_limiter_provider(prov)
            if prov == "GEMINI":
                _reset_rate_limiter_provider("GEMMA")
        logger.info("[key_renewal] Provider %s — mode=%s — %d/%d resetovano", prov, mode, len(results)-len(errors), len(results))
        return {"ok": len(errors)==0, "provider": prov, "mode": mode, "total": len(results), "success": len(results)-len(errors), "errors": errors, "results": results}
    except Exception as exc:
        logger.exception("[key_renewal] Greška pri provider renew %s", prov)
        return {"ok": False, "provider": prov, "error": str(exc), "results": results}
