# -*- coding: utf-8 -*-
"""core/stil.py — P4.1: mjerenje stila iz EPUB-a (EN original ili HR prijevod).

Cista statistika: bez AI, bez mreze, bez nltk/spacy (nema ih u Termuxu).
Isti ugovor za oba jezika da se EN i HR profil mogu usporediti (P4.3).

Mjeri: duzinu recenice (prosjek, medijan, % kratkih/dugih), udio dijaloga
(po odlomcima i po rijecima; crtica vs navodnici), omjer pasiva (samo EN,
heuristika), tipicne fraze (3-grami, samo EN).

NE zamjenjuje core/autor_analiza.py (taj daje tekstualni prompt iz prvih 30k znakova).
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

KRATKA_ISPOD = 10     # recenica s < 10 rijeci je kratka (kao core/autor_analiza.py)
DUGA_IZNAD = 25       # recenica s > 25 rijeci je duga
MIN_FRAZA = 6         # fraza mora imati bar toliko pojavljivanja
MAX_FRAZA = 20

# odlomak je dijalog ako pocinje crticom ili otvorenim navodnikom
_CRTICE = frozenset("—–-―")
_DIJ_START = frozenset('—–-―“"„»‘')

# fajlovi koji nisu proza (po imenu)
_ISKLJUCI_IMENA = ("toc", "nav", "cover", "titlepage", "title_page", "copyright",
                   "contents", "acknowledg", "about", "dedicat", "also_by", "alsoby",
                   "praise", "newsletter")

_SKR = frozenset("mr. mrs. ms. dr. st. jr. sr. prof. vs. etc. no. mt. capt. col. gen. lt. sgt. gov. rev.".split())
_KRAJ_RE = re.compile(r'([.!?…]+["”’»)\]]*)\s+')
_RIJEC_RE = re.compile(r"\w+(?:['’]\w+)*")

_STOP_EN = frozenset(
    "the a an and or but of to in on at for with by from as is was were be been he she it they we i "
    "you his her its their him them that this had have has not no so if then than".split())

_PASIV_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+"
    r"(?:(?:not|never|also|then|still|already|just|only|always|now|soon|finally|suddenly)\s+|\w+ly\s+)?"
    r"(\w+)", re.I)
_NEPRAVILNI = frozenset(
    "done made seen taken given known shown written broken chosen driven eaten fallen forgotten "
    "frozen gotten hidden ridden risen spoken stolen sworn thrown torn worn woken beaten begun "
    "bitten blown drawn flown grown held left lost kept sent built caught found led paid put read "
    "said sold set shot struck taught told thought won bound brought bought cut hit hurt laid lit "
    "met slain slung sung sunk woven".split())
_PASIV_ISKLJUCI = frozenset(
    "indeed hundred need speed breed creed exceed proceed succeed naked wicked sacred crooked "
    "beloved wretched ragged rugged jagged aged shed feed seed weed deed".split())


def _rijeci(s: str) -> list:
    return _RIJEC_RE.findall(s)


def _recenice(par: str) -> list:
    """Odlomak -> rečenice (kratice tipa Mr. i inicijali se ne režu)."""
    dijelovi = _KRAJ_RE.split(par)
    out, cur = [], ""
    for i, d in enumerate(dijelovi):
        if i % 2 == 0:
            cur += d
            continue
        cur += d
        tok = cur.split()[-1].lower() if cur.split() else ""
        if tok in _SKR or re.fullmatch(r"[a-z]\.", tok):
            cur += " "
            continue
        out.append(cur.strip())
        cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def _je_pasiv(s: str) -> bool:
    """EN heuristika: oblik 'to be' + particip (-ed ili nepravilni). Priblizno."""
    for m in _PASIV_RE.finditer(s):
        w = m.group(1).lower()
        if w in _PASIV_ISKLJUCI:
            continue
        if w in _NEPRAVILNI or (len(w) > 3 and w.endswith("ed")):
            return True
    return False


def _pct(a, b) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


def izdvoji_odlomke(epub_path) -> list:
    """EPUB -> lista odlomaka (plain tekst iz <p>), bez navigacije/naslovnica."""
    from bs4 import BeautifulSoup

    out = []
    with zipfile.ZipFile(epub_path) as z:
        imena = sorted(
            n for n in z.namelist()
            if n.lower().endswith((".html", ".xhtml", ".htm"))
            and not any(s in Path(n).name.lower() for s in _ISKLJUCI_IMENA)
        )
        for n in imena:
            try:
                raw = z.read(n).decode("utf-8", errors="replace")
            except (KeyError, OSError, zipfile.BadZipFile) as e:
                logger.warning("[stil] ne mogu citati %s: %s", n, e)
                continue
            soup = BeautifulSoup(raw, "html.parser")
            for nav in soup.find_all("nav"):
                nav.decompose()
            for p in soup.find_all("p"):
                t = re.sub(r"\s+", " ", p.get_text()).strip()
                if t and any(c.isalpha() for c in t):
                    out.append(t)
            # P4.4: goli tekst izvan <p> (body/div/blockquote, redovi odvojeni s <br>)
            for kont in soup.find_all(["body", "div", "blockquote"]):
                for dijete in kont.children:
                    if type(dijete).__name__ != "NavigableString":
                        continue
                    t = re.sub(r"\s+", " ", str(dijete)).strip()
                    if len(t) > 1 and any(c.isalpha() for c in t):
                        out.append(t)
    return out


def izmjeri(odlomci, jezik: str = "en") -> dict:
    """Lista odlomaka -> stilski profil (isti oblik za EN i HR)."""
    en = (jezik == "en")
    n_odl = len(odlomci)
    duzine = []
    pasivne = 0
    dij_odl = dij_rij = ukupno_rij = crtica = navodnik = 0
    trigrami = Counter()
    for par in odlomci:
        rp = len(_rijeci(par))
        ukupno_rij += rp
        prvi = par.lstrip()[:1]
        if prvi and prvi in _DIJ_START:
            dij_odl += 1
            dij_rij += rp
            if prvi in _CRTICE:
                crtica += 1
            else:
                navodnik += 1
        for s in _recenice(par):
            w = _rijeci(s)
            if not w:
                continue
            duzine.append(len(w))
            if en:
                if _je_pasiv(s):
                    pasivne += 1
                nizi = [x.lower() for x in w]
                for i in range(len(nizi) - 2):
                    g = nizi[i:i + 3]
                    if all(x in _STOP_EN for x in g):
                        continue
                    trigrami[" ".join(g)] += 1
    n_rec = len(duzine)
    if not n_rec:
        return {"verzija": 1, "jezik": jezik, "n_odlomaka": n_odl, "n_recenica": 0, "n_rijeci": ukupno_rij}
    return {
        "verzija": 1,
        "jezik": jezik,
        "n_odlomaka": n_odl,
        "n_recenica": n_rec,
        "n_rijeci": ukupno_rij,
        "prosj_rijeci_po_recenici": round(sum(duzine) / n_rec, 1),
        "median_rijeci_po_recenici": round(float(statistics.median(duzine)), 1),
        "kratke_pct": _pct(sum(1 for d in duzine if d < KRATKA_ISPOD), n_rec),
        "duge_pct": _pct(sum(1 for d in duzine if d > DUGA_IZNAD), n_rec),
        "prosj_rijeci_po_odlomku": round(ukupno_rij / n_odl, 1) if n_odl else 0.0,
        "dijalog_odlomaka_pct": _pct(dij_odl, n_odl),
        "dijalog_rijeci_pct": _pct(dij_rij, ukupno_rij),
        "crtica_pct_dijaloga": _pct(crtica, dij_odl),
        "navodnik_pct_dijaloga": _pct(navodnik, dij_odl),
        "pasiv_pct": _pct(pasivne, n_rec) if en else None,
        "fraze": [[f, c] for f, c in trigrami.most_common(MAX_FRAZA) if c >= MIN_FRAZA] if en else [],
        "pragovi": {"kratka_ispod": KRATKA_ISPOD, "duga_iznad": DUGA_IZNAD},
    }


def izmjeri_epube(putanje, autor: str, jezik: str = "en") -> dict:
    """Jedan ili vise EPUB-a istog autora -> jedan profil."""
    odl, izvori = [], []
    for p in putanje:
        o = izdvoji_odlomke(p)
        odl.extend(o)
        izvori.append({"datoteka": Path(p).name, "odlomaka": len(o)})
    prof = izmjeri(odl, jezik)
    prof["autor"] = autor
    prof["izvori"] = izvori
    return prof


def slug(autor: str) -> str:
    if autor and autor.count(",") == 1:
        _a, _b = [x.strip() for x in autor.split(",")]
        if _a and _b:
            autor = _b + " " + _a
    s = unicodedata.normalize("NFKD", autor or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "nepoznat_autor"


def spremi(profil: dict, autor: str, jezik: str = "en", root=None) -> Path:
    """data/stil/<slug>.json (EN) ili <slug>_<jezik>.json; atomicno."""
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    d = root / "data" / "stil"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (slug(autor) + ("" if jezik == "en" else "_" + jezik) + ".json")
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profil, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p


# ── P4.3: usporedba EN profila i HR prijevoda (za kapiju) ────────────────────
# Pragovi su pocetni (kalibrirani na 2 para: A Little Hatred, The Trouble with Peace);
# kapija ih koristi samo kao WARN dok se ne kalibriraju na TWOC-u (P4.4).
PRAGOVI = {"rec_min": 0.75, "rec_max": 1.25, "dij_min": 0.8, "dij_max": 1.25,
           "crtica_min": 80.0, "min_recenica": 200}


def usporedi(en: dict, hr: dict) -> list:
    """EN profil vs HR profil -> [(provjera, detalj)]; prazno = u granicama."""
    k = PRAGOVI
    if not isinstance(en, dict) or not isinstance(hr, dict):
        return []
    if min(en.get("n_recenica", 0), hr.get("n_recenica", 0)) < k["min_recenica"]:
        return []
    out = []
    a, b = en.get("prosj_rijeci_po_recenici"), hr.get("prosj_rijeci_po_recenici")
    if a and b is not None:
        r = b / a
        if not (k["rec_min"] <= r <= k["rec_max"]):
            out.append(("stil: duzina recenice HR/EN izvan %.2f-%.2f" % (k["rec_min"], k["rec_max"]),
                        "%.1f vs %.1f rijeci/recenici (omjer %.2f)" % (b, a, r)))
    a, b = en.get("dijalog_odlomaka_pct"), hr.get("dijalog_odlomaka_pct")
    if a and b is not None:
        r = b / a
        if not (k["dij_min"] <= r <= k["dij_max"]):
            out.append(("stil: udio dijaloga HR/EN izvan %.2f-%.2f" % (k["dij_min"], k["dij_max"]),
                        "%.1f%% vs %.1f%% odlomaka (omjer %.2f)" % (b, a, r)))
    cr = hr.get("crtica_pct_dijaloga") or 0
    if (hr.get("dijalog_odlomaka_pct") or 0) > 0 and cr < k["crtica_min"]:
        out.append(("stil: HR dijalog bez crtica (< %d%%)" % k["crtica_min"],
                    "crtica u %.1f%% dijaloga" % cr))
    return out


def osiguraj_en_profil(epub_path, root=None):
    """P4.4: ako za autora EN izvornika jos nema data/stil/<slug>.json, izmjeri ga i spremi.

    Preskace zbirke, knjige bez autora i knjige koje nisu na engleskom. Ne prepisuje postojeci profil.
    Vraca (status, putanja|None); nikad ne baca iznimku.
    """
    try:
        import html as _h
        epub_path = str(epub_path)
        try:
            from core.zbirka import je_zbirka
            zb, _r = je_zbirka(epub_path)
        except Exception:
            zb = False
        if zb:
            return "zbirka", None
        with zipfile.ZipFile(epub_path) as z:
            opf = next((n for n in z.namelist() if n.lower().endswith(".opf")), None)
            t = z.read(opf).decode("utf-8", "ignore") if opf else ""
        m = re.search(r"<dc:creator[^>]*>([^<]*)", t)
        autor = _h.unescape(m.group(1)).strip() if m else ""
        if not autor or autor.lower() in ("?", "va", "unknown", "sconosciuto", "nepoznat autor", "grupa autora"):
            return "bez_autora", None
        korijen = Path(root) if root else Path(__file__).resolve().parent.parent
        cilj = korijen / "data" / "stil" / (slug(autor) + ".json")
        if cilj.exists():
            return "postoji", cilj
        odl = izdvoji_odlomke(epub_path)
        tekst = " ".join(odl[:400]).lower()
        the = len(re.findall(r"\bthe\b", tekst))
        hrr = len(re.findall(r"\b(je|da|se)\b", tekst))
        if not (the > 50 and the > 3 * hrr):
            return "nije_en", None
        prof = izmjeri_epube([epub_path], autor, "en")
        if prof.get("n_recenica", 0) < MIN_RECENICA_PROFIL:
            return "premalo_teksta", None
        prof.setdefault("jezik", "en")
        return "spremljeno", spremi(prof, autor, "en", root=root)
    except Exception as e:  # noqa: BLE001 — prijevod se ne smije srusiti zbog stila
        return "greska: %s: %s" % (type(e).__name__, e), None


MIN_RECENICA_PROFIL = 200
