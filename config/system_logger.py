# config/system_logger.py
# ============================================================================
# SYSTEM LOGGER — Upisivanje svih logova u sistem.log fajl po datumu
#
# Log fajlovi: logs/sistem_DD-MM-YYYY.log
# Format:  [HH:MM:SS] LEVEL modul: poruka
#
# Koristi Python logging sa RotatingFileHandler + DailyRotation.
# Svaki novi dan → novi fajl. Stari se ne brišu automatski.
#
# Upotreba (iz bilo kojeg modula):
#   from config.system_logger import syslog
#   syslog.info("Poruka")
#   syslog.warning("Upozorenje")
#   syslog.error("Greška")
#   syslog.debug("Debug info")
#
# Integriše se i sa standardnim Python logging sistemom —
# sve poruke koje prođu kroz root logger (logging.getLogger())
# automatski idu i u sistem.log.
# ============================================================================

import logging
import threading
from datetime import datetime
from logging.handlers import BaseRotatingHandler
from pathlib import Path


# ── Putanja do log direktorija ────────────────────────────────────────────────
# logs/ direktorij u korijenu projekta (parent od config/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"

try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Fallback: radni direktorij
    _LOG_DIR = Path.cwd() / "logs"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Format log poruka ─────────────────────────────────────────────────────────
_LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

# Format datuma za ime fajla: DD-MM-YYYY
_FILE_DATE_FORMAT = "%d-%m-%Y"


def _current_log_path() -> Path:
    """Vraća putanju do log fajla za danas."""
    today = datetime.now().strftime(_FILE_DATE_FORMAT)
    return _LOG_DIR / f"sistem_{today}.log"


# ============================================================================
# DailyRotatingFileHandler — nova instanca fajla svakim danom
# ============================================================================

class DailyFileHandler(BaseRotatingHandler):
    """
    Handler koji radi rotaciju fajla svaki dan u ponoć.
    Naziv fajla: logs/sistem_DD-MM-YYYY.log
    Ne koristi time.sleep() — provjera je lazy (pri svakom emit pozivu).
    """

    def __init__(self, log_dir: Path, encoding: str = "utf-8"):
        self.log_dir = log_dir
        self._current_date = datetime.now().strftime(_FILE_DATE_FORMAT)
        filename = str(log_dir / f"sistem_{self._current_date}.log")
        super().__init__(filename, mode="a", encoding=encoding, delay=False)

    def shouldRollover(self, record) -> bool:  # noqa: N802
        """Rollover ako se datum promijenio."""
        today = datetime.now().strftime(_FILE_DATE_FORMAT)
        return today != self._current_date

    def doRollover(self):  # noqa: N802
        """Zatvori stari fajl, otvori novi za novi dan."""
        if self.stream:
            try:
                self.stream.flush()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        self._current_date = datetime.now().strftime(_FILE_DATE_FORMAT)
        self.baseFilename = str(self.log_dir / f"sistem_{self._current_date}.log")
        self.stream = self._open()

    def emit(self, record: logging.LogRecord):
        """Emit s automatskom rotacijom."""
        try:
            if self.shouldRollover(record):
                self.doRollover()
            super().emit(record)
        except Exception:
            self.handleError(record)


# ============================================================================
# Inicijalizacija system loggera
# ============================================================================

_init_lock = threading.Lock()
_initialized = False


def _initialize_system_logger() -> logging.Logger:
    """
    Kreira i konfigurira dedicirani 'system' logger koji upisuje u fajl.
    Poziva se jednom pri importu.
    """
    global _initialized

    with _init_lock:
        if _initialized:
            return logging.getLogger("system")

        # ── Dedicirani logger za sistem.log ───────────────────────────────────
        sys_logger = logging.getLogger("system")
        sys_logger.setLevel(logging.DEBUG)
        sys_logger.propagate = False  # ne propagira na root — izbjegava duplikate u logu

        # File handler — jedan fajl po danu
        file_handler = DailyFileHandler(_LOG_DIR)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        sys_logger.addHandler(file_handler)

        # ── Root logger file handler ──────────────────────────────────────────
        # Sve poruke iz SVIH modula (logging.getLogger(__name__)) idu i u fajl.
        root_logger = logging.getLogger()

        # Provjeri da nema duplikata (reload zaštita)
        existing_file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, DailyFileHandler)
        ]
        if not existing_file_handlers:
            root_file_handler = DailyFileHandler(_LOG_DIR)
            root_file_handler.setLevel(logging.DEBUG)
            root_file_handler.setFormatter(
                logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
            )
            root_logger.addHandler(root_file_handler)

        _initialized = True

        # Upiši startup marker u log
        today = datetime.now().strftime(_FILE_DATE_FORMAT)
        sys_logger.info(
            "=" * 70
        )
        sys_logger.info(
            "SISTEM LOG INICIJALIZIRAN — %s — log dir: %s",
            today, str(_LOG_DIR),
        )
        sys_logger.info(
            "=" * 70
        )

        return sys_logger


# ── Javni singleton ───────────────────────────────────────────────────────────
syslog: logging.Logger = _initialize_system_logger()


# ── Pomoćna funkcija za ostale module ────────────────────────────────────────

def get_current_log_path() -> Path:
    """Vraća apsolutnu putanju do trenutnog log fajla."""
    return _current_log_path()


def get_log_dir() -> Path:
    """Vraća direktorij gdje se čuvaju log fajlovi."""
    return _LOG_DIR


def list_log_files() -> list[Path]:
    """Lista svih sistem_*.log fajlova, sortirano od najstarijeg."""
    return sorted(_LOG_DIR.glob("sistem_*.log"))
