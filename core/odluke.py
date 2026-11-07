"""odluke: pamti korisnikove odluke na karticama revizije (append-only JSONL).

Odluke: ostavi (lazni alarm), prevedi_ponovo (stvarna greska), preskoci, ponisti.
Zadnja odluka po (knjiga, par) vrijedi; 'ponisti' je brise.
"""
import hashlib
import json
import re
import time
from pathlib import Path

PUTANJA = Path(__file__).resolve().parent.parent / "data" / "odluke.jsonl"
ODLUKE = ("ostavi", "prevedi_ponovo", "preskoci")


def kljuc(en, hr):
    """Stabilan kljuc para (EN fragment, HR fragment), neosjetljiv na razmake i velika slova."""
    def n(s):
        return re.sub(r"\s+", " ", str(s or "")).strip().lower()
    return hashlib.sha1((n(en) + "\x1f" + n(hr)).encode("utf-8")).hexdigest()[:16]


def _citaj():
    if not PUTANJA.exists():
        return []
    out = []
    for i, linija in enumerate(PUTANJA.read_text("utf-8").splitlines(), 1):
        linija = linija.strip()
        if not linija:
            continue
        try:
            out.append(json.loads(linija))
        except json.JSONDecodeError:
            print(f"[odluke] neispravan redak {i} preskocen")
    return out


def zabiljezi(knjiga, blok, en, hr, tip, odluka, novo=""):
    """Dodaje jednu odluku na kraj fajla. Vraca zapis."""
    if odluka not in ODLUKE + ("ponisti",):
        raise ValueError(f"nepoznata odluka: {odluka}")
    PUTANJA.parent.mkdir(parents=True, exist_ok=True)
    zap = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "knjiga": knjiga, "blok": blok,
           "en": en, "hr": hr, "tip": tip, "odluka": odluka, "novo": novo,
           "kljuc": kljuc(en, hr)}
    with PUTANJA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(zap, ensure_ascii=False) + "\n")
    return zap


def _stanje():
    st = {}
    for z in _citaj():
        k = (z.get("knjiga"), z.get("kljuc"))
        if z.get("odluka") == "ponisti":
            st.pop(k, None)
        else:
            st[k] = z
    return st


def je_odbacen(en, hr):
    """True ako je ovaj par ikad oznacen 'ostavi' (kartica se vise ne prikazuje)."""
    k = kljuc(en, hr)
    return any(z["kljuc"] == k and z["odluka"] == "ostavi" for z in _stanje().values())


def za_automatsko_prevodjenje(en, hr, prag=2):
    """True ako je isti par bar 'prag' puta oznacen 'prevedi_ponovo' (u razlicitim knjigama/blokovima)."""
    k = kljuc(en, hr)
    n = sum(1 for z in _stanje().values() if z["kljuc"] == k and z["odluka"] == "prevedi_ponovo")
    return n >= prag


def statistika():
    """{tip: {ostavi, prevedi_ponovo, preskoci, preciznost}}; preciznost = prevedi/(prevedi+ostavi)."""
    s = {}
    for z in _stanje().values():
        d = s.setdefault(z.get("tip", "?"), {"ostavi": 0, "prevedi_ponovo": 0, "preskoci": 0})
        d[z["odluka"]] += 1
    for d in s.values():
        u = d["ostavi"] + d["prevedi_ponovo"]
        d["preciznost"] = round(d["prevedi_ponovo"] / u, 2) if u else None
    return s
