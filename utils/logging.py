

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
        shared_stats["live_audit"] = "".join(audit_logs)



