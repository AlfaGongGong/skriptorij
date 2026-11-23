import os as _os_v; _os_v.environ.setdefault("BOOKLYFI_VERIFIER", "1")  # verifikator ukljucen po defaultu
_os_v.environ.setdefault("BOOKLYFI_VERIFIER_FIX", "1")  # P2.19.3: verifikator ponovno prevodi flagirane blokove (kvaliteta > brzina)
import atexit
import contextlib
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# Uvoz fabrike aplikacije i dijeljenog stanja
from app import app
from config.logging_config import configure_logging
from config.settings import PORT, SHARED_CONTROLS, SHARED_STATS

logger = logging.getLogger("booklyfi.main")

# ── Putanje ──────────────────────────────────────────────────────────────────
# Prilagodi ako su tvoje putanje drugačije
_BASE = Path(__file__).parent
# Koristi apsolutne putanje iz config/settings.py
try:
    from config.settings import INPUT_DIR as _CFG_INPUT_DIR

    PROJECTS_ROOT = str(_CFG_INPUT_DIR)
    INPUT_DIR = str(_CFG_INPUT_DIR)
except ImportError:
    PROJECTS_ROOT = os.environ.get("PROJECTS_ROOT", str(_BASE / "projects"))
    INPUT_DIR = os.environ.get("INPUT_DIR", str(_BASE / "data"))

_INTRO_LOADED = True

# ANSI boje
_GREEN = "\x1b[1;92m"
_RED = "\x1b[1;91m"
_BRED = "\x1b[1;97;41m"
_YELLOW = "\x1b[1;93m"
_CYAN = "\x1b[1;96m"
_RESET = "\x1b[0m"

_AUDIT_INTERVAL = 300  # sekundi (5 minuta)


# ============================================================================
# FLASK AUDIT THREAD
# ============================================================================
def _flask_audit_loop(port: int) -> None:
    """Svakih 5 minuta provjerava dostupnost Flask servera."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/status"
    time.sleep(15)

    while True:
        ts = time.strftime("%H:%M:%S")
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = resp.getcode()
                status = SHARED_STATS.get("status", "?")
                pct = SHARED_STATS.get("pct", 0)
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


_SERVER_ZNAKOVI = ("main.py", "run.py", "app.py", "booklyfi", "skriptorij")


def _pid_je_nasa(pid: int, znakovi=_SERVER_ZNAKOVI):
    """L62a: True ako cmdline procesa izgleda kao nas server, False ako je to
    tudi proces (PID iz starog fajla se reciklirao), None ako se ne moze procitati."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    cmd = raw.replace(b"\x00", b" ").decode("utf-8", "ignore").lower()
    if not cmd.strip():
        return None
    return any(z in cmd for z in znakovi)


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

    if _pid_je_nasa(old_pid) is False:
        print(
            f"{_YELLOW}[BOOKLYFI]{_RESET} PID {old_pid} iz starog fajla nije nas server — ne diram taj proces."
        )
        _PID_FILE.unlink(missing_ok=True)
        return

    print(
        f"{_YELLOW}[BOOKLYFI]{_RESET} Zatečena živa instanca (PID {old_pid}) — gasim je..."
    )
    try:
        os.kill(old_pid, signal.SIGTERM)
    except ProcessLookupError:
        _PID_FILE.unlink(missing_ok=True)
        return
    except PermissionError:
        print(
            f"{_RED}[BOOKLYFI]{_RESET} Nemam dozvolu da ugasim PID {old_pid} — nastavljam, moguć je konflikt na portu."
        )
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
    with contextlib.suppress(OSError):
        _PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file() -> None:
    with contextlib.suppress(OSError):
        _PID_FILE.unlink(missing_ok=True)


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================
def _graceful_shutdown(_signum, _frame):
    SHARED_CONTROLS["stop"] = True
    SHARED_STATS["status"] = "ZAUSTAVLJENO"
    print(
        f"\n{_YELLOW}[SHUTDOWN] Signal primljen — čekam završetak tekuće obrade...{_RESET}"
    )
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
        with contextlib.suppress(Exception):
            book = json.loads(lbp.read_text("utf-8")).get("last_book", "")
    return book


def _termux_wake_lock():
    if shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"], check=False)
    else:
        print(f"{_YELLOW}[WARN]{_RESET} termux-api nije instaliran, wake-lock preskočen")


def _termux_wake_unlock():
    if shutil.which("termux-wake-unlock"):
        subprocess.run(["termux-wake-unlock"], check=False)
    else:
        print(f"{_YELLOW}[WARN]{_RESET} termux-api nije instaliran, wake-unlock preskočen")




# ── Gemini TTS proxy endpoint (2026-11-02) ─────────────────────────────────
# Lokalni endpoint za TTS Server plugin. Flask radi Gemini API iz Pythona,
# plugin zove 127.0.0.1:8080/tts/gemini. Zaobilazi drake.net probleme.

# ── TTS filter: zaseban thread i status (ne gazi prevod) ──────────────────
_TTS_JOB = {"stats": None, "thread": None}


@app.route("/api/tts/start", methods=["POST"])
def api_tts_start():
    import copy
    import os
    import threading
    from flask import request, jsonify
    from config.settings import INPUT_DIR, SHARED_STATS

    data = request.get_json(silent=True) or {}
    book = data.get("book")
    model = data.get("model") or "V10_TURBO"
    if not book:
        return jsonify({"error": "Nije odabrana knjiga"}), 400
    th = _TTS_JOB.get("thread")
    if th is not None and th.is_alive():
        return jsonify({"error": "TTS filter je već u toku"}), 409
    full_path = os.path.join(str(INPUT_DIR), book)
    if not os.path.exists(full_path):
        return jsonify({"error": "Fajl '" + str(book) + "' ne postoji u " + str(INPUT_DIR)}), 404
    try:
        stats = copy.deepcopy(SHARED_STATS)
    except Exception:
        stats = dict(SHARED_STATS)
    stats.update({
        "status": "POKRETANJE (TTS)...", "pct": 0, "live_audit": "",
        "output_file": "", "current_file": book,
        "audit_events": [], "audit_next_id": 1,
    })
    try:
        from config.settings import SHARED_CONTROLS
        controls = dict(SHARED_CONTROLS)
    except Exception:
        controls = {}
    controls.update({"stop": False, "pause": False, "reset": False})
    _TTS_JOB["stats"] = stats

    def _run():
        try:
            from tts import start_from_master as _start_tts
            _start_tts(full_path, model, stats, controls)
        except Exception as exc:
            stats["status"] = "GREŠKA (TTS): " + type(exc).__name__
            stats["live_audit"] = str(stats.get("live_audit", "")) + "<div>" + str(exc) + "</div>"

    t = threading.Thread(target=_run, daemon=True)
    _TTS_JOB["thread"] = t
    t.start()
    return jsonify({"status": "Started", "file": book, "tool": "TTS"})


@app.route("/api/tts/status", methods=["GET"])
def api_tts_status():
    from flask import jsonify
    st = _TTS_JOB.get("stats")
    if not st:
        return jsonify({"status": "IDLE", "pct": 0, "live_audit": "", "output_file": ""})
    return jsonify({
        "status": str(st.get("status", "")),
        "pct": st.get("pct", 0),
        "live_audit": str(st.get("live_audit", "")),
        "output_file": str(st.get("output_file", "")),
    })


@app.route("/tts/gemini", methods=["POST"])
def tts_gemini_endpoint():
    """Body: {"text": "...", "voice": "Kore", "keys": ["..."]}
    Vraca: WAV (audio/wav) ili JSON gresku."""
    import json as _json
    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
    from flask import request, jsonify

    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        voice = data.get("voice", "Kore")
        keys = data.get("keys") or []
        if not text:
            return jsonify({"error": "Prazan text"}), 400
        if not keys:
            # fallback: ucitaj iz dev_api.json
            try:
                with open("dev_api.json", encoding="utf-8") as f:
                    keys = _json.load(f).get("GEMINI", [])
            except Exception:
                pass
        if not keys:
            return jsonify({"error": "Nema Gemini kljuceva"}), 400

        # sanitizacija voice
        ALL = ["Kore","Puck","Charon","Fenrir","Aoede","Leda","Orus","Zephyr",
               "Autonoe","Enceladus","Iapetus","Umbriel","Algieba","Despina",
               "Erinome","Algenib","Rasalgethi","Laomedeia","Achernar","Alnilam",
               "Schedar","Gacrux","Pulcherrima","Achird","Zubenelgenubi",
               "Vindemiatrix","Sadachbia","Sadaltager","Sulafat"]
        voice_name = "Kore"
        for v in ALL:
            if v in str(voice):
                voice_name = v
                break

        # 2026-11-05: Podrska za custom glasove (voice_...) i prebuilt (Charon, Kore...)
        if voice_name.startswith("voice_"):
            _voice_cfg = {"voiceConfig": {"voice": voice_name}}
        else:
            _voice_cfg = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}

        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": _voice_cfg
            }
        }
        model = "gemini-3.1-flash-tts-preview"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        last_err = ""
        for i, k in enumerate(keys):
            try:
                req = _urllib_req.Request(
                    url,
                    data=_json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json", "x-goog-api-key": k},
                    method="POST",
                )
                with _urllib_req.urlopen(req, timeout=30) as r:
                    resp = _json.loads(r.read().decode("utf-8"))
                parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "inlineData" in p and p["inlineData"].get("data"):
                        import base64 as _b64
                        import subprocess as _subprocess
                        import tempfile as _tempfile
                        pcm = _b64.b64decode(p["inlineData"]["data"])
                        
                        # Konvertujemo sirovi PCM u MP3 preko ffmpeg
                        with _tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as _f_in:
                            _f_in.write(pcm)
                            _in_path = _f_in.name
                        _out_path = _in_path + ".mp3"
                        try:
                            _subprocess.run([
                                "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                                "-i", _in_path, "-codec:a", "libmp3lame", "-b:a", "128k", _out_path
                            ], check=True, capture_output=True, timeout=10)
                            with open(_out_path, "rb") as _f_out:
                                _mp3_data = _f_out.read()
                        finally:
                            if __import__("os").path.exists(_in_path): __import__("os").remove(_in_path)
                            if __import__("os").path.exists(_out_path): __import__("os").remove(_out_path)
                            
                        from flask import Response as _Resp
                        return _Resp(_mp3_data, mimetype="audio/mpeg")
                last_err = f"K{i+1}: nema audio"
            except _urllib_err.HTTPError as e:
                last_err = f"K{i+1}: HTTP {e.code}"
                if e.code == 429:
                    continue
            except Exception as e:
                last_err = f"K{i+1}: {str(e)[:80]}"
        return jsonify({"error": "Svi kljucevi pali", "last": last_err}), 502
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── Kraj Gemini TTS endpoint ────────────────────────────────────────────────

if __name__ == "__main__":
    import os as _os
    _host = _os.environ.get("BOOKLYFI_HOST", "127.0.0.1")
    configure_logging(logging.ERROR)
    os.system("clear" if os.name == "posix" else "cls")

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    _kill_previous_instance()
    _write_pid_file()

    if _host not in ("127.0.0.1", "localhost", "::1") and not _os.environ.get("BOOKLYFI_TOKEN"):
        import secrets as _secrets

        _os.environ["BOOKLYFI_TOKEN"] = _secrets.token_urlsafe(12)
        print(
            f"{_YELLOW}[BOOKLYFI]{_RESET} Server je dostupan s mreže ({_host}); drugi uređaji trebaju token."
            f" Otvori s drugog uređaja: http://<IP>:{PORT}/?token={_os.environ['BOOKLYFI_TOKEN']}"
        )
    print(f"{_GREEN}[BOOKLYFI]{_RESET} Server na http://{_host}:{PORT}…")
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
                rc = subprocess.run([TERMUX_OPEN, url], capture_output=True)
                if rc != 0:
                    print(
                        f"{_YELLOW}[BOOKLYFI]{_RESET} termux-open-url exit {rc} — otvori ručno: {url}"
                    )
            else:
                if not webbrowser.open(url):
                    print(
                        f"{_YELLOW}[BOOKLYFI]{_RESET} Browser se nije otvorio — otvori ručno: {url}"
                    )
        except Exception:
            logger.debug("[C3_fallback] main.py:221 Exception")

    threading.Thread(target=_open_browser, daemon=True).start()

    threading.Thread(
        target=_flask_audit_loop,
        args=(PORT,),
        daemon=True,
        name="flask-audit",
    ).start()

    _termux_wake_lock()
    atexit.register(_termux_wake_unlock)

    try:
        app.run(
            host=_host, port=PORT, debug=False, use_reloader=False, threaded=True
        )
    except Exception as exc:
        sys.stdout.write(
            f"{_BRED}[KRITIČNA GREŠKA] Flask se nije pokrenuo: "
            f"{type(exc).__name__}: {exc}{_RESET}\n"
        )
        sys.stdout.write(traceback.format_exc())
        sys.stdout.flush()
        sys.exit(1)
    finally:
        _termux_wake_unlock()
        _remove_pid_file()