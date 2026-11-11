"""P2.15 gate: cirilica -> latinica (automatski), ekavizmi/srbizmi kratki popis pravila (P6.1, samo upozorenje)."""
import re

_C = "абвгдђежзијклљмнњопрстћуфхцчџш"
_L = ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o",
      "p", "r", "s", "t", "ć", "u", "f", "h", "c", "č", "dž", "š"]
_TBL = {}
for _c, _l in zip(_C, _L):
    _TBL[ord(_c)] = _l
    _TBL[ord(_c.upper())] = _l.capitalize()
_CIR_RE = re.compile(r"[\u0400-\u04FF]")
_EKAV = re.compile(
    r"\b(dete|deteta|detetu|deca|decu|mleko|pesma|pesme|mesto|posle|vreme|tačno|tačan|tačna|"
    r"ceo|cela|celo|lepo|lepa|hteo|htela|htelo|reka|reke)\b",
    re.I,
)


def cir2lat(t):
    return (t or "").translate(_TBL)


def broj_cirilice(t):
    return len(_CIR_RE.findall(t or ""))


def gate_blok(tekst):
    """-> (tekst, info). Cirilica se translitera; ekavizmi samo u info."""
    info = []
    n = broj_cirilice(tekst)
    if n:
        tekst = cir2lat(tekst)
        info.append(f"ćirilica→latinica ({n} znakova)")
    plain = re.sub(r"<[^>]+>", " ", tekst or "")
    m = _EKAV.findall(plain)
    if m:
        info.append("ekavizmi: " + ", ".join(sorted({x.lower() for x in m})[:6]))
    return tekst, "; ".join(info)
