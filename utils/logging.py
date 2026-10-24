import json as _json_b8
import time


"""
utils/logging.py — Audit log builder za Booklyfi

Tipovi poruka:
  critical  → crvena  (KRITIČNA greška — zaustavlja rad)
  error     → crvena  (greška, ali moguć nastavak) — alias za critical u displayu
  warning   → žuta    (upozorenje, rad se nastavlja)
  success   → zelena  (uspješna operacija)
  system    → ljubičasta (sistemske poruke — inicijalizacija, reset...)
  tech      → siva    (tehničke/mrežne poruke, debug info)
  info      → siva    (generalne info poruke, default)
  accordion → sirovi HTML (za složene prikaze)
"""

from datetime import datetime
import logging as _stdlib_logging
import re

_AUDIT_FILE_LOGGER = _stdlib_logging.getLogger("skriptorij.audit")

audit_logs: list[str] = []
MAX_AUDIT_LINES = 500

# FIX friendly-log: prepoznaje ceste tehnicke poruke i pretvara ih u
# razumljiviju recenicu za UI. Original poruka NIKAD ne nestaje - ide
# u en_text (postojeci pod-linija mehanizam) i i dalje u file logger.
_FRIENDLY_PATTERNS = [
    (re.compile(r"^\[?([A-Z]+)\]?.*prazan odgovor.*"),
     lambda m: f"\u21bb {m.group(1)} nije vratio potpun odgovor, pokusavam ponovo s vise prostora za tekst"),
    (re.compile(r"tpm_gate"),
     lambda m: "\u23f3 Kratka pauza zbog ogranicenja brzine servisa, nastavljam za par sekundi"),
    (re.compile(r"^([A-Z]+).*\u2192.*\b(429|500|503)\b"),
     lambda m: f"\u26a0\ufe0f {m.group(1)} trenutno ne odgovara kako treba, prebacujem se na sljedeci servis"),
    (re.compile(r"Svi provideri iscrpljeni za blok (\d+)"),
     lambda m: f"\u274c Nijedan servis nije uspio obraditi dio {m.group(1)} \u2014 pokusacu ponovo kasnije"),
    (re.compile(r"Sumnja na halucinaciju"),
     lambda m: "\U0001f50e Provjeravam ispravnost prevoda, trazim bolju verziju"),
    (re.compile(r"^\[([A-Z]+)\] HTTP 429"),
     lambda m: f"\u23f3 {m.group(1)} je privremeno zauzet, cekam kratko pa nastavljam"),
    (re.compile(r"^\[([A-Z]+)\] Mrezna greska|^\[([A-Z]+)\] Mrežna greška"),
     lambda m: f"\U0001f50c Prekid veze sa {m.group(1) or m.group(2)}, pokusavam ponovo"),
]


def _simplify_message(msg: str):
    """FIX friendly-log: vraca (friendly, original) - original prazan ako nema izmjene."""
    for pattern, builder in _FRIENDLY_PATTERNS:
        m = pattern.search(msg)
        if m:
            try:
                return builder(m), msg
            except Exception:
                return msg, ""
    return msg, ""


def add_audit(msg: str, atype: str = "info", en_text: str = "", shared_stats=None) -> None:
    """
    Dodaje entry u audit log i ažurira shared_stats["live_audit"].

    Parametri:
        msg         — poruka za prikaz
        atype       — tip poruke: critical | error | warning | success | system | tech | info | accordion
        en_text     — opcionalni dodatni tekst (npr. EN izvornik)
        shared_stats — dict koji se dijeli s pollingom (live_audit ključ)
    """

    # 2026-10-24 C1: dual-write JSON u SHARED_STATS["audit_events"]
    # (delegira na add_structured; ne dira postojeci HTML live_audit string)
    try:
        _nivo_json = atype if atype in ("info", "warning", "error", "debug") else "info"
        add_structured(_nivo_json, "audit", msg[:100],
                       en_text=(en_text or "")[:200])
    except Exception:
        pass

    global audit_logs

    # Spoji na pravi file logger da warning/critical/error audit poruke
    # zavrse u logs/sistem_*.log -- inace se gube kad shared_stats["live_audit"]
    # rotira preko MAX_AUDIT_LINES ili proces restartuje.
    if atype in ("critical", "error"):
        _AUDIT_FILE_LOGGER.error(msg)
    elif atype == "warning":
        _AUDIT_FILE_LOGGER.warning(msg)

    _friendly, _tech_detail = _simplify_message(msg)
    if _tech_detail and not en_text:
        en_text = _tech_detail
    msg = _friendly

    ts = datetime.now().strftime("%H:%M:%S")

    if atype == "system":
        # Ljubičasta — sistemske poruke (inicijalizacija, pokretanje, reset)
        entry = (
            f"<div class='log-entry log-system'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-label'>SYS</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    elif atype in ("critical", "error"):
        # Crvena — kritična greška koja može zaustaviti rad
        entry = (
            f"<div class='log-entry log-critical'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-label'>GREŠKA</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    elif atype == "warning":
        # Žuta — upozorenje, rad se može nastaviti
        entry = (
            f"<div class='log-entry log-warning'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-label'>UPOZ</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    elif atype == "success":
        # Zelena — uspješna operacija
        entry = (
            f"<div class='log-entry log-success'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-label'>OK</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    elif atype == "tech":
        # Siva, manja — mrežne/tehničke poruke
        entry = (
            f"<div class='log-entry log-tech'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-label'>NET</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    elif atype == "accordion":
        # Sirovi HTML blok (npr. EN/HR preview)
        entry = f"<div class='log-entry log-accordion'>{en_text}</div>"

    else:
        # info / default — siva, standardna veličina
        entry = (
            f"<div class='log-entry log-info'>"
            f"<span class='log-ts'>{ts}</span>"
            f"<span class='log-msg'>{msg}</span>"
            f"{'<div class=log-sub>' + en_text + '</div>' if en_text else ''}"
            f"</div>"
        )

    audit_logs.append(entry)

    # Drži samo zadnjih MAX_AUDIT_LINES zapisa
    if len(audit_logs) > MAX_AUDIT_LINES:
        audit_logs = audit_logs[-MAX_AUDIT_LINES:]

    if shared_stats is not None:
        # Dedupe — modul-level _AUDIT_LAST (NE u SHARED_STATS — jsonify ne moze tuple kljuceve)
        import threading as _threading
        global _AUDIT_LAST, _AUDIT_LAST_LOCK
        if "_AUDIT_LAST" not in globals():
            _AUDIT_LAST = {}
        if "_AUDIT_LAST_LOCK" not in globals():
            _AUDIT_LAST_LOCK = _threading.Lock()

        with _AUDIT_LAST_LOCK:
            _now_ts = time.time()
            _key = (atype, msg[:120])
            _prev = _AUDIT_LAST.get(_key, {})
            if (_prev.get("ts", 0) > _now_ts - 2.0
                    and _prev.get("nivo") == atype):
                _prev["count"] = _prev.get("count", 1) + 1
                _prev["ts"] = _now_ts
                _AUDIT_LAST[_key] = _prev
                _events = shared_stats.get("audit_events", [])
                if _events:
                    _events[-1]["tekst"] = msg + " (×" + str(_prev["count"]) + ")"
                shared_stats["live_audit"] = "".join(audit_logs)
                return
            else:
                _AUDIT_LAST[_key] = {"ts": _now_ts, "nivo": atype, "count": 1}

        shared_stats["live_audit"] = "".join(audit_logs)
        # ── Paralelno strukturirano (JSON za /api/monitor/audit) ──
        if "audit_events" not in shared_stats:
            shared_stats["audit_events"] = []
            shared_stats["audit_next_id"] = 1
        _eid = shared_stats["audit_next_id"]
        shared_stats["audit_next_id"] = _eid + 1
        shared_stats["audit_events"].append({
            "id": _eid,
            "nivo": atype,
            "tekst": msg,
            "sub": en_text,
            "ts": ts,
        })
        if len(shared_stats["audit_events"]) > 500:
            shared_stats["audit_events"] = shared_stats["audit_events"][-500:]

# ─────────────────────────────────────────────────────────────────────────────
# B8-lite (2026-10-24): strukturirano JSON logiranje.
# Postojeci logger.info/warning/error pozivi rade nepromenjeno (plain text).
# Novi kod moze da koristi add_structured() za JSON dogadjaje.
# ─────────────────────────────────────────────────────────────────────────────

_STRUCTURED_LOG = True


def add_structured(nivo: str, modul: str, event: str, **kwargs):
    """
    Strukturirani JSON log u live_audit (i logger.info kao plain text fallback).

    Args:
        nivo: "info" | "warning" | "error" | "debug"
        modul: "styler" | "pipeline" | "http_client" | "fleet" | "discovery" | ...
        event: kratki naziv dogadjaja (npr. "gemini_503", "cache_miss")
        **kwargs: dodatni kontekst (provider, key_mask, chunk_idx, latency_ms, ...)

    Primer:
        add_structured("warning", "http_client", "gemini_503",
                       provider="GEMINI", key_mask="...Yxkg", chunk_idx=42,
                       latency_ms=1500)
    """
    import time as _t_b8
    entry = {
        "ts": round(_t_b8.time(), 3),
        "nivo": nivo,
        "modul": modul,
        "event": event,
        **{k: v for k, v in kwargs.items() if v is not None},
    }
    # Plain text fallback (postojeci logger) — SAMO za module koji nemaju vlastiti file logger
    # 2026-10-24 C1: modul="audit" preskacemo — add_audit vec ima _AUDIT_FILE_LOGGER,
    # a taj logger je kroz handler rekurzivno pozivao add_structured (5 eventa umesto 3).
    if modul != "audit":
        try:
            msg = "[" + modul + "] " + event
            if kwargs:
                msg += " | " + " ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
            _logger_func = {
                "info": logger.info,
                "warning": logger.warning,
                "error": logger.error,
                "debug": logger.debug,
            }.get(nivo, logger.info)
            _logger_func(msg)
        except Exception:
            pass
    # 2026-10-24 C1: strukturirani zapis u SHARED_STATS["audit_events"]
    # (config.settings.SHARED_STATS — pravi objekat, ne utils.shared_state)
    try:
        from config.settings import SHARED_STATS
        if "audit_events" not in SHARED_STATS:
            SHARED_STATS["audit_events"] = []
        if "audit_next_id" not in SHARED_STATS:
            SHARED_STATS["audit_next_id"] = 1
        entry["id"] = SHARED_STATS["audit_next_id"]
        SHARED_STATS["audit_next_id"] += 1
        SHARED_STATS["audit_events"].append(entry)
        if len(SHARED_STATS["audit_events"]) > 1000:
            SHARED_STATS["audit_events"] = SHARED_STATS["audit_events"][-1000:]
    except Exception:
        pass
    return entry
