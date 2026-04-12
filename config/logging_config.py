"""Konfiguracija logginga za Skriptorij."""
import logging


def configure_logging(level: int = logging.ERROR) -> None:
    """Postavi log level za werkzeug i root logger."""
    logging.getLogger("werkzeug").setLevel(level)
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
