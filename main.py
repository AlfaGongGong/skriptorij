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

# Uvoz fabrike aplikacije i dijeljenog stanja
from app import app
from config.settings import PORT, SHARED_STATS, SHARED_CONTROLS
from config.logging_config import configure_logging

# Introspect intro — standalone /intro route is always active via app.py
_INTRO_LOADED = True


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================
def _graceful_shutdown(signum, frame):
    """Postavi stop flag i završi aktivnu obradu."""
    SHARED_CONTROLS["stop"] = True
    SHARED_STATS["status"] = "ZAUSTAVLJENO"
    print("\n\x1b[1;93m[SHUTDOWN] Signal primljen — čekam završetak tekuće obrade...\x1b[0m")
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
    print("\x1b[1;92m" + "=" * 48 + "\x1b[0m")
    print("\x1b[1;96m  🚀 SKRIPTORIJ V8 TURBO - SERVER AKTIVAN 🚀  \x1b[0m")
    print("\x1b[1;92m" + "=" * 48 + "\x1b[0m")
    print(f"\x1b[1;93m [INFO]\x1b[0m http://127.0.0.1:{PORT}")
    if _INTRO_LOADED:
        print("\x1b[1;95m [INFO] Kinematski intro: AKTIVAN\x1b[0m")
    print("\n\x1b[1;31m >>> CTRL+C za zaustavljanje <<<\x1b[0m\n")

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
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
