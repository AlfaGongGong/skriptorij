import os
import signal
import sys
import threading
import time
import logging
import webbrowser
import traceback
import json
from pathlib import Path

# Uvoz fabrike aplikacije i dijeljenog stanja
from app import app
from config.settings import PORT, SHARED_STATS, SHARED_CONTROLS
from config.logging_config import configure_logging

# ── Putanje ──────────────────────────────────────────────────────────────────
# Prilagodi ako su tvoje putanje drugačije
_BASE = Path(__file__).parent
# Koristi apsolutne putanje iz config/settings.py
try:
    from config.settings import INPUT_DIR as _CFG_INPUT_DIR
    PROJECTS_ROOT = str(_CFG_INPUT_DIR)
    INPUT_DIR     = str(_CFG_INPUT_DIR)
except ImportError:
    PROJECTS_ROOT = os.environ.get("PROJECTS_ROOT", str(_BASE / "projects"))
    INPUT_DIR     = os.environ.get("INPUT_DIR",     str(_BASE / "data"))

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
    """Svakih 5 minuta provjerava dostupnost Flask servera."""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}/api/status"
    time.sleep(15)

    while True:
        ts = time.strftime("%H:%M:%S")
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code   = resp.getcode()
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
# PID FAJL — sprječava dvostruko pokretanje servera
# ============================================================================
# FIX: dodano da se main.py moze pokrenuti ponovo bez rucnog ubijanja
# prethodne instance — sprjecava "Address already in use" pri restartu.
_PID_FILE = _BASE / ".skriptorij_server.pid"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Proces postoji ali nije nas (drugi user) — tretiraj kao živ.
        return True
    return True


def _kill_previous_instance() -> None:
    """Ako je stara instanca servera i dalje živa (po PID fajlu), gasi je
    prije nego nova krene."""
    if not _PID_FILE.exists():
        return
    try:
        old_pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        _PID_FILE.unlink(missing_ok=True)
        return

    if old_pid == os.getpid() or not _pid_is_alive(old_pid):
        _PID_FILE.unlink(missing_ok=True)
        return

    print(f"{_YELLOW}[BOOKLYFI]{_RESET} Zatečena živa instanca (PID {old_pid}) — gasim je...")
    try:
        os.kill(old_pid, signal.SIGTERM)
    except ProcessLookupError:
        _PID_FILE.unlink(missing_ok=True)
        return
    except PermissionError:
        print(f"{_RED}[BOOKLYFI]{_RESET} Nemam dozvolu da ugasim PID {old_pid} — nastavljam, moguć je konflikt na portu.")
        return

    for _ in range(20):  # do ~5 sekundi
        if not _pid_is_alive(old_pid):
            break
        time.sleep(0.25)
    else:
        print(f"{_RED}[BOOKLYFI]{_RESET} PID {old_pid} se ne gasi — šaljem SIGKILL...")
        try:
            os.kill(old_pid, signal.SIGKILL)
            time.sleep(0.5)
        except ProcessLookupError:
            pass

    _PID_FILE.unlink(missing_ok=True)


def _write_pid_file() -> None:
    try:
        _PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def _remove_pid_file() -> None:
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================
def _graceful_shutdown(signum, frame):
    SHARED_CONTROLS["stop"] = True
    SHARED_STATS["status"]  = "ZAUSTAVLJENO"
    print(f"\n{_YELLOW}[SHUTDOWN] Signal primljen — čekam završetak tekuće obrade...{_RESET}")
    _remove_pid_file()
    sys.exit(0)


# ============================================================================
# POMOĆNA FUNKCIJA — aktivna knjiga
# ============================================================================
def _resolve_book() -> str:
    """Vraća naziv aktivne knjige iz SHARED_STATS ili last_book.json."""
    book = SHARED_STATS.get("current_file", "")
    if book:
        return book
    lbp = _BASE / "last_book.json"  # uvijek relativno od projekta
    if lbp.exists():
        try:
            book = json.loads(lbp.read_text("utf-8")).get("last_book", "")
        except Exception:
            pass
    return book

if __name__ == "__main__":
    configure_logging(logging.ERROR)
    os.system("clear" if os.name == "posix" else "cls")

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT,  _graceful_shutdown)

    _kill_previous_instance()
    _write_pid_file()

    print(f"{_GREEN}[BOOKLYFI]{_RESET} Server na http://127.0.0.1:{PORT}…")
    if _INTRO_LOADED:
        print(f"{_CYAN}[BOOKLYFI]{_RESET} Intro animacija: AKTIVAN")
    print(f"{_YELLOW}[BOOKLYFI]{_RESET} CTRL+C za zaustavljanje.\n")

    def _open_browser():
        time.sleep(1.5)
        # FIX: cache-bust query param — tjera browser da povuce svjezu
        # stranicu umjesto stare iz keša/service workera (bez rucnog
        # hard-refresha nakon svakog restarta servera).
        url = f"http://127.0.0.1:{PORT}/?_fresh={int(time.time())}"
        try:
            TERMUX_OPEN = "/data/data/com.termux/files/usr/bin/termux-open-url"
            if os.path.exists(TERMUX_OPEN):
                rc = os.system(f"{TERMUX_OPEN} {url} > /dev/null 2>&1")
                if rc != 0:
                    print(f"{_YELLOW}[BOOKLYFI]{_RESET} termux-open-url exit {rc} — otvori ručno: {url}")
            else:
                if not webbrowser.open(url):
                    print(f"{_YELLOW}[BOOKLYFI]{_RESET} Browser se nije otvorio — otvori ručno: {url}")
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()

    threading.Thread(
        target=_flask_audit_loop,
        args=(PORT,),
        daemon=True,
        name="flask-audit",
    ).start()

    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as exc:
        sys.stdout.write(
            f"{_BRED}[KRITIČNA GREŠKA] Flask se nije pokrenuo: "
            f"{type(exc).__name__}: {exc}{_RESET}\n"
        )
        sys.stdout.write(traceback.format_exc())
        sys.stdout.flush()
        sys.exit(1)
    finally:
        _remove_pid_file()
