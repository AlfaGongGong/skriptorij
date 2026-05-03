

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
from typing import Optional

audit_logs: list[str] = []
MAX_AUDIT_LINES = 180


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



