"""
main.py — Ulazna tačka za Skriptorij V8 Turbo server.

Importuje Flask app instancu iz app.py (fabrika) i pokreće server.
Zadržana kompatibilnost s direktnim pokretanjem: python main.py
"""

import os
import signal
import sys
import threading
import time
import logging
import webbrowser
import traceback

# Uvoz fabrike aplikacije i dijeljenog stanja
from app import app
from config.settings import PORT, SHARED_STATS, SHARED_CONTROLS
from config.logging_config import configure_logging

# Introspect intro — standalone /intro route is always active via app.py
_INTRO_LOADED = True

# ANSI boje
_GREEN  = "\x1b[1;92m"
_RED    = "\x1b[1;91m"
_BRED   = "\x1b[1;97;41m"
_YELLOW = "\x1b[1;93m"
_CYAN   = "\x1b[1;96m"
_RESET  = "\x1b[0m"

_AUDIT_INTERVAL = 300  # sekundi (5 minuta)


# ============================================================================
# FLASK AUDIT THREAD
# ============================================================================
def _flask_audit_loop(port: int) -> None:
    """Svakih 5 minuta provjerava dostupnost Flask servera i ispisuje u terminal."""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}/api/status"

    # Sačekaj da se server podigne prije prvog audita
    time.sleep(15)

    while True:
        ts = time.strftime("%H:%M:%S")
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = resp.getcode()
                status = SHARED_STATS.get("status", "?")
                pct    = SHARED_STATS.get("pct", 0)
                engine = SHARED_STATS.get("active_engine", "---")
                sys.stdout.write(
                    f"{_GREEN}[AUDIT {ts}] ✅ Flask OK (HTTP {code}) | "
                    f"status={status} | pct={pct}% | engine={engine}{_RESET}\n"
                )
                sys.stdout.flush()
        except urllib.error.URLError as exc:
            sys.stdout.write(
                f"{_BRED}[AUDIT {ts}] ❌ FLASK NEDOSTUPAN — {exc.reason}{_RESET}\n"
            )
            sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(
                f"{_RED}[AUDIT {ts}] ⚠️  Audit greška: {type(exc).__name__}: {exc}{_RESET}\n"
            )
            sys.stdout.flush()

        time.sleep(_AUDIT_INTERVAL)


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================
def _graceful_shutdown(signum, frame):
    """Postavi stop flag i završi aktivnu obradu."""
    SHARED_CONTROLS["stop"] = True
    SHARED_STATS["status"] = "ZAUSTAVLJENO"
    print(f"\n{_YELLOW}[SHUTDOWN] Signal primljen — čekam završetak tekuće obrade...{_RESET}")
    sys.exit(0)


# ============================================================================
# POKRETANJE SERVERA
# ============================================================================
if __name__ == "__main__":
    configure_logging(logging.ERROR)
    os.system("clear" if os.name == "posix" else "cls")

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    print("\x1b[1;91m  ____  _         _       _             _ _ \x1b[0m")
    print("\x1b[1;91m / ___|| | ___ __(_)_ __ | |_ ___  _ __(_) |\x1b[0m")
    print("\x1b[1;91m \\___ \\| |/ / '__| | '_ \\| __/ _ \\| '__| | |\x1b[0m")
    print("\x1b[1;91m  ___) |   <| |  | | |_) | || (_) | |  | | |\x1b[0m")
    print("\x1b[1;91m |____/|_|\\_\\_|  |_| .__/ \\__\\___/|_|  |_| |\x1b[0m")
    print("\x1b[1;91m                   |_|                      \x1b[0m")
    print(f"{_GREEN}" + "=" * 48 + f"{_RESET}")
    print(f"{_CYAN}  🚀 SKRIPTORIJ V8 TURBO - SERVER AKTIVAN 🚀  {_RESET}")
    print(f"{_GREEN}" + "=" * 48 + f"{_RESET}")
    print(f"{_YELLOW} [INFO]{_RESET} http://127.0.0.1:{PORT}")
    if _INTRO_LOADED:
        print(f"\x1b[1;95m [INFO] Kinematski intro: AKTIVAN{_RESET}")
    print(f"\x1b[1;96m [INFO] Flask audit: svakih {_AUDIT_INTERVAL // 60} min{_RESET}")
    print(f"\n{_RED} >>> CTRL+C za zaustavljanje <<<{_RESET}\n")

    def open_browser():
        time.sleep(1.5)
        try:
            if os.path.exists("/data/data/com.termux/files/usr/bin/termux-open-url"):
                os.system(f"termux-open-url http://127.0.0.1:{PORT} > /dev/null 2>&1")
            else:
                webbrowser.open(f"http://127.0.0.1:{PORT}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    # Pokretanje audit threada
    threading.Thread(
        target=_flask_audit_loop,
        args=(PORT,),
        daemon=True,
        name="flask-audit",
    ).start()

    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as exc:
        sys.stdout.write(
            f"{_BRED}[KRITIČNA GREŠKA] Flask server se nije pokrenuo: "
            f"{type(exc).__name__}: {exc}{_RESET}\n"
        )
        sys.stdout.write(traceback.format_exc())
        sys.stdout.flush()
        sys.exit(1)
