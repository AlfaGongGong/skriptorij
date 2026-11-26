# -*- coding: utf-8 -*-
"""
core/tipografija.py — JEDINI modul koji dira navodnike, crtice i trotočje.

Cilj (konačni oblik):
  • umetnuti navodnici  → „…”  (U+201E / U+201D), nikad ASCII "
  • replika             → — na početku odlomka
  • trotočje            → …

API:
  normaliziraj(tekst)        HTML ili običan tekst → normaliziran string
  normaliziraj_soup(soup)    in-place nad BeautifulSoup/Tag, vraća broj izmijenjenih čvorova
  provjeri(tekst, strogo)    lista problema (ništa ne mijenja); strogo=True → AssertionError

Pravila rada:
  • radi nad TEKSTUALNIM ČVOROVIMA (BeautifulSoup), nikad regex nad HTML-om
  • stanje navodnika se vodi po odlomku preko granica tagova (<em>, <span> drop-cap...)
  • ne dira riječi (nema kalkova); atributi i tagovi ostaju netaknuti
  • idempotentno: normaliziraj(normaliziraj(x)) == normaliziraj(x)
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)

OTV = "\u201e"
ZAT = "\u201d"
_TOGGLE = "\"\u201c\u00ab\u00bb"
_SVE = _TOGGLE + OTV + ZAT
_CRTICE = ("\u2014", "\u2013")
_VELIKO = "A-ZČĆŠŽĐ"
_BLOK = ["p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
         "div", "td", "th", "dd", "dt", "figcaption", "caption"]
_PRESKOCI = {"script", "style", "pre", "code", "title"}
_JE_HTML = re.compile(r"</?[A-Za-z][^>]*>")


# ── znakovi s vlasnikom (indeks tekstualnog čvora) ──────────────────────────

def _spoji(z):
    return "".join(c for c, _ in z)


def _primijeni(z, izmjene):
    """izmjene: [(start, end, novo)] nepreklapajuće; novo nasljeđuje vlasnika prvog znaka."""
    if not izmjene:
        return z
    out, poz = [], 0
    for s, e, novo in sorted(izmjene):
        out.extend(z[poz:s])
        vl = z[s][1] if s < len(z) else (z[-1][1] if z else 0)
        out.extend((c, vl) for c in novo)
        poz = e
    out.extend(z[poz:])
    return out


def _regex(z, pattern, repl, flags=0):
    t = _spoji(z)
    izm = [(m.start(), m.end(), m.expand(repl)) for m in re.finditer(pattern, t, flags)]
    return _primijeni(z, izm)


# ── navodnici ───────────────────────────────────────────────────────────────

def _prolaz(t):
    zam, otvoren, src, opos, stray = [], False, None, -1, []
    for i, c in enumerate(t):
        if c in _TOGGLE:
            if not otvoren and i > 0 and t[i - 1].isdigit():
                continue  # znak za inče (5"), ne navodnik
            if otvoren:
                zam.append((i, i + 1, ZAT))
                otvoren = False
            else:
                zam.append((i, i + 1, OTV))
                otvoren, src, opos = True, "toggle", i
        elif c == OTV:
            otvoren, src, opos = True, "forced", i
        elif c == ZAT:
            if otvoren:
                otvoren = False
            else:
                stray.append(i)
    return zam, otvoren, src, opos, stray


def _zatvarajuci(t, i):
    """navodnik zalijepljen za prethodnu riječ, iza njega razmak/interpunkcija/kraj."""
    return (i > 0 and not t[i - 1].isspace()
            and (i + 1 >= len(t) or t[i + 1].isspace() or t[i + 1] in ",;:.!?\u2026)"))


# ── L50: replika u navodnicima na početku odlomka → crtica ───────────────────
# Odluka korisnika (17.11.): dijalog je u CRTICAMA od početka. Odlomak koji
# počinje navodnikom postaje replika samo ako se može pouzdano prepoznati:
#   • citat završava .!?… ili zarezom, ILI iza njega slijedi „, malo-slovo“ (oznaka govornika),
#   • ILI je navodnik nezatvoren (govor se nastavlja u idućem odlomku).
# Ostalo (npr. „Dobar dan” je bila šifra; „Reče”, „da” i „ne”) ostaje u navodnicima.
_OTVARACI = _TOGGLE + OTV
_ZATVARACI = _TOGGLE + ZAT
_KRAJ_REC = ".!?\u2026"
_RX_ODMAH_OTV = re.compile(r"[,;]?\s*([" + re.escape(_OTVARACI) + r"])")


def _kraj_citata(t, o):
    for i in range(o + 1, len(t)):
        if t[i] in _ZATVARACI:
            return i
    return -1


def _je_replika(s, ostatak):
    st = s.rstrip()
    if not st:
        return False
    if st[-1] in _KRAJ_REC or st[-1] == ",":
        return True
    return bool(re.match(r",\s*[a-zčćšžđ]", ostatak))


def _replike_u_crtice(z):
    """Nove znakove ako odlomak počinje replikom u navodnicima, inače None."""
    t = _spoji(z)
    lead = len(t) - len(t.lstrip())
    if lead >= len(t) or t[lead] not in _OTVARACI:
        return None
    c = _kraj_citata(t, lead)
    if c == -1:
        return _primijeni(z, [(lead, lead + 1, "\u2014 ")])
    if not _je_replika(t[lead + 1:c], t[c + 1:]):
        return None
    izm = [(lead, lead + 1, "\u2014 ")]
    o = lead
    while c != -1:
        s, rest = t[o + 1:c], t[c + 1:]
        if not rest.strip():
            izm.append((c, c + 1, ""))
            break
        m_next = _RX_ODMAH_OTV.match(rest)
        if s.rstrip().endswith(",") or re.match(r"\s*[\u2014\u2013]", rest):
            izm.append((c, c + 1, ""))
            nar = c + 1
        elif m_next:
            o2 = c + 1 + m_next.start(1)
            izm.append((c, o2 + 1, " \u2014 "))
            o, c = o2, _kraj_citata(t, o2)
            continue
        else:
            m = re.match(r"[,;]?\s*", rest)
            izm.append((c, c + 1 + m.end(), " \u2014 "))
            nar = c + 1 + m.end()
        j = next((i for i in range(nar, len(t)) if t[i] in _OTVARACI), -1)
        if j == -1:
            break
        k = j
        while k > nar and t[k - 1].isspace():
            k -= 1
        if k > nar and t[k - 1] == ",":
            k -= 1
        izm.append((k, j + 1, " \u2014 "))
        o, c = j, _kraj_citata(t, j)
    return _primijeni(z, izm)


def _navodnici(z):
    t = _spoji(z)
    if not any(c in t for c in _SVE):
        return z
    t = _spoji(z)
    lead = len(t) - len(t.lstrip())
    dash = t[lead:lead + 1] in _CRTICE
    if not dash:
        nz = _replike_u_crtice(z)
        if nz is not None:
            z = nz
            t = _spoji(z)
            lead = len(t) - len(t.lstrip())
            dash = True

    zam, otv, src, opos, stray = _prolaz(t)
    if otv and src == "toggle":
        izm = None
        if not dash and opos == lead and t[opos + 1:opos + 2].strip():
            izm = (opos, opos + 1, "— ")          # siroče-otvarač → crtica replike
            dash = True
        elif dash or _zatvarajuci(t, opos):
            izm = (opos, opos + 1, "")            # siroče → briše se
        if izm:
            z = _primijeni(z, [izm])
            t = _spoji(z)
            zam, otv, src, opos, stray = _prolaz(t)
    izm = list(zam)
    if dash:
        izm += [(i, i + 1, "") for i in stray]    # siroče ” u odlomku s crticom
    return _primijeni(z, izm)


def _blok(z):
    z = _regex(z, r"\.{3,}|\.\s\.\s\.", "\u2026")
    z = _regex(z, r"(?<![.\u2026])\.\.(?![.\u2026])", ".")
    z = _regex(z, r"^\s*--\s*", "\u2014 ")
    z = _regex(z, rf"^(\s*)[-\u2013\u2014]\s+(?=[{_VELIKO}\"\u201e\u201c\u00bb\u00ab])", "\\1\u2014 ")
    z = _regex(z, r"^(\s*)\u2014(?=[^\s\u2014])", "\\1\u2014 ")
    z = _regex(z, r"(?<=\S)--(?=\S)", "\u2014")
    z = _regex(z, r"\s+--\s+", " \u2014 ")
    # en-crtica samo za raspone godina (1990-1995) i stranica (str. 10-20); telefoni i datumi ostaju
    z = _regex(z, r"(?<![\d-])((?:1[0-9]|20)\d\d)\s*-\s*((?:1[0-9]|20)\d\d)(?![\d-])", "\\1\u2013\\2")
    z = _regex(z, r"\b((?:str|pp|p|s)\.\s*)(\d+)\s*-\s*(\d+)(?![\d-])", "\\1\\2\u2013\\3")
    z = _regex(z, r"(?<=[^\s\u2014])\u2014(?=[^\s\u2014])", " \u2014 ")
    z = _navodnici(z)
    z = _regex(z, r",,+", ",")
    z = _regex(z, r"(?<=\S)\s+(?=[,;:!?])", "")
    z = _regex(z, r"  +", " ")
    return z


# ── enumeracija blokova ─────────────────────────────────────────────────────

def _cvorovi(el):
    return [n for n in el.find_all(string=True)
            if type(n) is NavigableString
            and not any(p.name in _PRESKOCI for p in n.parents)]


def _grupe(soup):
    grupe, pokriveno = [], set()
    for el in soup.find_all(_BLOK):
        if el.find(_BLOK):
            continue
        g = _cvorovi(el)
        if g:
            grupe.append(g)
            pokriveno.update(id(n) for n in g)
    for n in _cvorovi(soup):
        if id(n) not in pokriveno and n.strip():
            grupe.append([n])
    return grupe


# ── javni API ───────────────────────────────────────────────────────────────

def normaliziraj_soup(soup) -> int:
    n = 0
    for g in _grupe(soup):
        z = [(c, i) for i, t in enumerate(g) for c in str(t)]
        novi = _blok(z)
        tekstovi = ["".join(c for c, o in novi if o == i) for i in range(len(g))]
        for node, nt in zip(g, tekstovi):
            if nt != str(node):
                node.replace_with(nt)
                n += 1
    return n


def normaliziraj(tekst: str) -> str:
    if not tekst:
        return tekst
    if _JE_HTML.search(tekst):
        soup = BeautifulSoup(tekst, "html.parser")
        return str(soup) if normaliziraj_soup(soup) else tekst
    izlaz = []
    for linija in tekst.split("\n"):
        z = [(c, 0) for c in linija]
        izlaz.append(_spoji(_blok(z)))
    return "\n".join(izlaz)


def provjeri(tekst: str, strogo: bool = False) -> list:
    """Samo provjerava. Vraća listu problema; strogo=True baca AssertionError."""
    if _JE_HTML.search(tekst or ""):
        grupe = [[str(n) for n in g] for g in _grupe(BeautifulSoup(tekst, "html.parser"))]
    else:
        grupe = [[l] for l in (tekst or "").split("\n")]
    pr = []
    for g in grupe:
        t = "".join(g)
        lead = t.lstrip()
        ctx = lead[:60].replace("\n", " ")
        if any(c in t for c in _TOGGLE):
            pr.append(f"ASCII/tuđi navodnik: {ctx}")
        if lead.startswith(("-", "--")):
            pr.append(f"ASCII crtica na početku: {ctx}")
        if "..." in t:
            pr.append(f"tri tačke umjesto …: {ctx}")
        if lead[:1] in _CRTICE and ZAT in t and t.count(ZAT) > t.count(OTV):
            pr.append(f"siroče ” u odlomku s crticom: {ctx}")
        elif t.count(OTV) != t.count(ZAT):
            pr.append(f"nebalansirano „ ”: {ctx}")
    if strogo and pr:
        raise AssertionError("tipografija: " + "; ".join(pr[:5]))
    return pr
