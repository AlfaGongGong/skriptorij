"""G19: lore enforcement — zamjena odbacenih varijanti kanonskim terminima.

- zamjena samo u tekstu izvan HTML tagova (atributi ostaju netaknuti)
- cijela rijec (bez dijelova drugih rijeci); padezi se NAMJERNO ne diraju
- velika slova se prilagodjavaju: pocetak recenice -> kanon s velikim pocetnim, VERZALI -> VERZALI
- zamjena je doslovna (backslash i \\g<..> u kanonskoj rijeci nemaju posebno znacenje)
"""
import re

_TAG = re.compile(r"(<[^>]*>)")


def _prilagodi_velika(nadjeno: str, hr: str) -> str:
    if len(nadjeno) > 1 and nadjeno.isupper() and not hr.isupper():
        return hr.upper()
    if nadjeno[:1].isupper() and hr[:1].islower():
        return hr[:1].upper() + hr[1:]
    return hr


def _pravila(termini):
    pravila = []
    for en, info in (termini or {}).items():
        if not isinstance(info, dict):
            continue
        hr = info.get("hr", en)
        if not isinstance(hr, str) or not hr:
            continue
        for bad in info.get("odbacene_varijante", []) or []:
            if not isinstance(bad, str) or not bad or bad.lower() == hr.lower():
                continue
            pravila.append((re.compile(r"(?<!\w)" + re.escape(bad) + r"(?!\w)", re.IGNORECASE), hr))
    return pravila


def primijeni_kanon(tekst: str, termini: dict):
    """Vraca (novi_tekst, broj_zamjena)."""
    pravila = _pravila(termini)
    if not pravila or not tekst:
        return tekst, 0
    ukupno = 0
    dijelovi = _TAG.split(tekst)
    for i, d in enumerate(dijelovi):
        if i % 2 == 1 or not d:
            continue
        for rx, hr in pravila:
            d, n = rx.subn(lambda m, hr=hr: _prilagodi_velika(m.group(0), hr), d)
            ukupno += n
        dijelovi[i] = d
    return "".join(dijelovi), ukupno
