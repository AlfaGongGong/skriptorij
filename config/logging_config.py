"""Konfiguracija logginga za Skriptorij."""
import logging
import sys


def configure_logging(level: int = logging.ERROR) -> None:
    """Postavi log level za werkzeug i root logger.

    ERROR i CRITICAL poruke uvijek idu na stdout kako bi bile vidljive
    u terminalu bez obzira na postavljeni level.
    """
    logging.getLogger("werkzeug").setLevel(level)

    # Standardni handler za zadani level
    root = logging.getLogger()
    root.setLevel(min(level, logging.ERROR))

    # Ukloni eventualnu duplu konfiguraciju
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(handler)

    # Dedicirani handler koji uvijek ispisuje ERROR i CRITICAL u terminal
    class _CriticalTerminalHandler(logging.StreamHandler):
        """Ispisuje ERROR/CRITICAL poruke direktno u terminal (stdout)."""
        COLORS = {
            logging.CRITICAL: "\x1b[1;97;41m",  # bijelo na crvenom
            logging.ERROR:    "\x1b[1;91m",       # svijetlocrveno
        }
        RESET = "\x1b[0m"

        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.ERROR:
                color = self.COLORS.get(record.levelno, self.COLORS[logging.ERROR])
                msg = self.format(record)
                try:
                    sys.stdout.write(f"{color}[KRITIČNO] {msg}{self.RESET}\n")
                    sys.stdout.flush()
                except Exception:
                    self.handleError(record)

    crit_handler = _CriticalTerminalHandler(sys.stdout)
    crit_handler.setLevel(logging.ERROR)
    crit_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    # Dodaj samo ako već nema identičan handler (izbjegni duplikate pri reload-u)
    existing_types = [type(h).__name__ for h in root.handlers]
    if "_CriticalTerminalHandler" not in existing_types:
        root.addHandler(crit_handler)
