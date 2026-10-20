"""
core/metrics.py — deterministicke metrike kvaliteta teksta.

Brojaci gresaka umjesto ocjene 1-10: uporedivo izmedju knjiga i kroz vrijeme.
Cista funkcija: bez AI poziva, bez mijenjanja postojeceg koda.
"""
import html
import re
from collections import Counter

from core.kalkovi.ekavizmi import EKAVIZMI
from core.quality import _ekstrahuj_cist_tekst
from core.text_utils import _detektuj_en_ostatke

# Pasusi kraci od ovoga se ne broje kao duplikati ("Da." u dijalogu je normalno)
MIN_RECI_DUPLIKAT = 4

_RE_RIJEC = re.compile(r"[^\W_]+")
_RE_P = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_BLOK = re.compile(r"</?(?:p|div|br|h[1-6]|li|blockquote|tr)\b[^>]*>", re.IGNORECASE)
_RE_RAZMAK = re.compile(r"[.,;:!?](?=[^\W\d_])")
_RE_CRTICA = re.compile(r"^\s*-\s*[^\W\d_]")
_RE_VELIKO = re.compile(r"([^\s.!?]+)([.!?])\s+(?=[^\W\d_])")

_SKRACENICE = frozenset({
    "itd", "itp", "tj", "npr", "tzv", "ur", "god", "br", "sv", "str", "usp",
    "dr", "mr", "prof", "gđa", "gđica", "gosp", "sl", "vs", "etc", "cf", "mj",
    "tel", "ul", "ing", "dipl", "inž", "doc", "akad", "sr", "cca",
})

_KOMPILIRANI = None


def _nule() -> dict:
    return {
        "ekavizmi_per_1000": 0.0,
        "en_ostaci_per_1000": 0.0,
        "duplikati": 0,
        "ratio_source_target": None,
        "tipografija_greske": 0,
        "reci_ukupno": 0,
    }


def _cist(tekst) -> str:
    try:
        return _ekstrahuj_cist_tekst(tekst) or ""
    except Exception:
        return ""


def _pasusi(tekst: str) -> list:
    """Pasusi iz HTML-a (<p>) ili plain texta (\\n\\n). JSON (.chk) se prvo ekstrahuje."""
    if tekst.lstrip().startswith("{"):
        tekst = _cist(tekst)
    nadjeno = _RE_P.findall(tekst)
    if nadjeno:
        izvori = nadjeno
    else:
        izvori = re.split(r"\n\s*\n", _RE_BLOK.sub("\n\n", tekst))
    out = []
    for iz in izvori:
        p = html.unescape(_RE_TAG.sub("", iz))
        if p.strip():
            out.append(p)
    return out


def _ekavizmi_obrasci() -> list:
    global _KOMPILIRANI
    if _KOMPILIRANI is None:
        lista = []
        for stavka in EKAVIZMI:
            try:
                lista.append(re.compile(stavka[0], re.IGNORECASE))
            except re.error:
                continue
        _KOMPILIRANI = lista
    return _KOMPILIRANI


def _broji_ekavizme(cist: str) -> int:
    """Pogodci koji se preklapaju (npr. 'pre nego sto' i 'pre nego') broje se jednom."""
    spans = []
    for rx in _ekavizmi_obrasci():
        for m in rx.finditer(cist):
            if m.end() > m.start():
                spans.append((m.start(), m.end()))
    if not spans:
        return 0
    spans.sort()
    n = 0
    kraj = -1
    for s, e in spans:
        if s >= kraj:
            n += 1
            kraj = e
        else:
            kraj = max(kraj, e)
    return n


def _broji_duplikate(pasusi: list) -> int:
    cnt = Counter()
    for p in pasusi:
        norm = " ".join(p.lower().split())
        if len(_RE_RIJEC.findall(norm)) >= MIN_RECI_DUPLIKAT:
            cnt[norm] += 1
    return sum(c - 1 for c in cnt.values() if c > 1)


def _tipografija_pasus(p: str) -> int:
    p = p.strip()
    n = 0

    # dupli razmak (novi redovi iz HTML formatiranja se ne racunaju)
    n += len(re.findall(r" {2,}", re.sub(r"\s*\n\s*", " ", p)))

    # nedostajuci razmak iza interpunkcije (kad slijedi slovo)
    for tok in p.split():
        if "@" in tok or "://" in tok or tok.lower().startswith("www."):
            continue
        for m in _RE_RAZMAK.finditer(tok):
            i = m.start()
            znak = tok[i]
            if znak == ".":
                if i > 0 and tok[i - 1] == ".":
                    continue  # tropoint
                if not tok[i + 1].isupper():
                    continue  # domena/fajl/skracenica, ne recenica
                if i > 0 and tok[i - 1].isalpha() and (i < 2 or not tok[i - 2].isalnum()):
                    continue  # inicijal ili d.o.o.
            n += 1

    # dijalog sa crticom (-) umjesto em-dash
    for linija in p.splitlines():
        if _RE_CRTICA.match(linija):
            n += 1

    # malo slovo iza kraja recenice
    for m in _RE_VELIKO.finditer(p):
        pre, znak = m.group(1), m.group(2)
        if znak == "." and (pre.isdigit() or len(pre) == 1 or pre.lower() in _SKRACENICE):
            continue
        if p[m.end()].islower():
            n += 1
    return n


def _navodnici_greske(tekst: str) -> int:
    """Nespareni navodnici po tipu. ASCII " se ne mesa sa „ “."""
    n = 0
    # ASCII "..." — paran broj (svaki otvoreni ima zatvoreni)
    n += tekst.count('"') % 2
    # „...“ (njemacki) — otv mora biti == zatv
    n += abs(tekst.count("\u201e") - tekst.count("\u201c"))
    # ”...” (francuski, samo zatvoreni) — samo ako nema „
    if tekst.count("\u201e") == 0:
        n += abs(tekst.count("\u201c") - tekst.count("\u201d"))
    # «...» — paran
    n += abs(tekst.count("\u00ab") - tekst.count("\u00bb"))
    # ‘...’ — paran
    n += abs(tekst.count("\u2018") - tekst.count("\u2019"))
    return n


def _tipografija(pasusi: list) -> int:
    n = sum(_tipografija_pasus(p) for p in pasusi)
    return n + _navodnici_greske("\n".join(pasusi))


def compute_metrics(text: str, source: str | None = None) -> dict:
    """
    Racuna metrike za tekst (i opciono izvor).

    Returns:
        ekavizmi_per_1000, en_ostaci_per_1000, duplikati,
        ratio_source_target (None bez izvora), tipografija_greske, reci_ukupno
    """
    if not isinstance(text, str) or not text.strip():
        return _nule()

    cist = _cist(text)
    reci = len(_RE_RIJEC.findall(cist))
    if reci == 0:
        return _nule()

    ratio = None
    if isinstance(source, str) and source.strip():
        reci_src = len(_RE_RIJEC.findall(_cist(source)))
        if reci_src > 0:
            ratio = round(reci_src / reci, 4)

    pasusi = _pasusi(text)
    return {
        "ekavizmi_per_1000": round(_broji_ekavizme(cist) / reci * 1000, 2),
        "en_ostaci_per_1000": round(_detektuj_en_ostatke(cist) * 1000, 2),
        "duplikati": _broji_duplikate(pasusi),
        "ratio_source_target": ratio,
        "tipografija_greske": _tipografija(pasusi),
        "reci_ukupno": reci,
    }
