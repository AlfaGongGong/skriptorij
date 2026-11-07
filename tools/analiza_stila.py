#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/analiza_stila.py — P4.1: izmjeri stil iz EPUB-a i spremi data/stil/<autor>.json.

Primjeri:
  python3 tools/analiza_stila.py --autor "Joe Abercrombie" original.epub [drugi.epub ...]
  python3 tools/analiza_stila.py --autor "Joe Abercrombie" --jezik hr prijevod.epub
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import stil  # noqa: E402

_PRIKAZ = ("n_odlomaka", "n_recenica", "n_rijeci", "prosj_rijeci_po_recenici",
           "median_rijeci_po_recenici", "kratke_pct", "duge_pct", "dijalog_odlomaka_pct",
           "dijalog_rijeci_pct", "crtica_pct_dijaloga", "navodnik_pct_dijaloga", "pasiv_pct")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P4.1 mjerenje stila iz EPUB-a")
    ap.add_argument("epub", nargs="+")
    ap.add_argument("--autor", required=True)
    ap.add_argument("--jezik", choices=("en", "hr"), default="en")
    ap.add_argument("--bez-upisa", action="store_true", help="samo ispis, bez data/stil/*.json")
    a = ap.parse_args(argv)
    for p in a.epub:
        if not Path(p).is_file():
            print("Nema fajla:", p, file=sys.stderr)
            return 2
    prof = stil.izmjeri_epube(a.epub, a.autor, a.jezik)
    if not prof.get("n_recenica"):
        print("Nema teksta u <p> oznakama; profil nije napravljen.", file=sys.stderr)
        return 1
    for k in _PRIKAZ:
        print("%-28s %s" % (k, prof.get(k)))
    if prof.get("fraze"):
        print("fraze (top 8):", "; ".join("%s x%d" % (f, c) for f, c in prof["fraze"][:8]))
    if not a.bez_upisa:
        print("Upisano:", stil.spremi(prof, a.autor, a.jezik))
    return 0


if __name__ == "__main__":
    sys.exit(main())
