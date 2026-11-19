"""G20 / DIO 2: provjera da stilizator ne pravi EPUB koji je ostao engleski.

Mjeri se udio engleskih stop-rijeci u tijelu svakog dokumenta. Vec hrvatski
EPUB-ovi prolaze (nizak udio, dijakritici); EN izvor bez spojenog prijevoda ne.
"""
import re

from core.text_utils import _EN_STOPWORDS, _HR_DIACRITICALS

MIN_RIJECI = 120      # kraci dokumenti (naslovnica, impresum) se ne ocjenjuju
PRAG_DOKUMENT = 0.06  # udio EN stop-rijeci iznad kojeg je dokument "engleski"
PRAG_UDIO = 0.25      # udio engleskih dokumenata u knjizi iznad kojeg se odbija
MIN_EN_DOKUMENATA = 2

_TAG = re.compile(r"<[^>]+>")
_HEAD = re.compile(r"<head\b.*?</head>|<title\b.*?</title>", re.I | re.S)
_RIJEC = re.compile(r"[a-z]{2,}")


def en_udio(html: str):
    """(udio EN stop-rijeci, broj rijeci, HR dijakritika) za tijelo dokumenta."""
    tekst = _TAG.sub(" ", _HEAD.sub(" ", html or ""))
    low = tekst.lower()
    rijeci = _RIJEC.findall(low)
    hr = sum(1 for c in low if c in _HR_DIACRITICALS)
    if not rijeci:
        return 0.0, 0, hr
    en = sum(1 for w in rijeci if w in _EN_STOPWORDS)
    return en / len(rijeci), len(rijeci), hr


def dokument_je_engleski(html: str) -> bool:
    udio, n, hr = en_udio(html)
    if n < MIN_RIJECI:
        return False
    if hr / max(1, n) > 0.02:  # izrazit HR dijakritik: hrvatski tekst
        return False
    return udio >= PRAG_DOKUMENT


def ocijeni_knjigu(dokumenti):
    """dokumenti: iterable (ime, html). Vraca (ok, poruka, statistika)."""
    ocjenjeni, engleski = 0, []
    for ime, html in dokumenti:
        _, n, _ = en_udio(html)
        if n < MIN_RIJECI:
            continue
        ocjenjeni += 1
        if dokument_je_engleski(html):
            engleski.append(str(ime))
    stat = {"ocjenjeno": ocjenjeni, "engleskih": len(engleski), "primjeri": engleski[:5]}
    if ocjenjeni and len(engleski) >= min(MIN_EN_DOKUMENATA, ocjenjeni) and len(engleski) / ocjenjeni >= PRAG_UDIO:
        return False, "engleskih dokumenata %d od %d (npr. %s)" % (
            len(engleski), ocjenjeni, ", ".join(stat["primjeri"][:3])), stat
    return True, "", stat
