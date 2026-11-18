"""L61: redaktor tajni (API kljuceva) za logove i poruke gresaka."""
import logging
import re

_RX = (
    (re.compile(r"([?&]key=)[^&\s'\"]+", re.I), r"\1***"),
    (re.compile(r"(x-goog-api-key['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+", re.I), r"\1***"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "AIza***"),
    (re.compile(r"\bgsk_[0-9A-Za-z]{16,}"), "gsk_***"),
)


def redaktiraj(tekst) -> str:
    s = str(tekst)
    for rx, zamjena in _RX:
        s = rx.sub(zamjena, s)
    return s


def instaliraj_redaktor() -> None:
    """Omota LogRecord tvornicu: svaka log poruka prolazi kroz redaktiraj()."""
    stara = logging.getLogRecordFactory()
    if getattr(stara, "_redakt", False):
        return

    def tvornica(*a, **k):
        r = stara(*a, **k)
        try:
            r.msg = redaktiraj(r.getMessage())
            r.args = ()
        except Exception:
            pass
        return r

    tvornica._redakt = True
    logging.setLogRecordFactory(tvornica)
