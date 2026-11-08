"""P2.6i: izvjestaj o preciznosti teskih gresaka verifikatora iz korisnikovih odluka (samo citanje).
preciznost = prevedi_ponovo / (prevedi_ponovo + ostavi), po tipu, s Wilson 95% rasponom.
Pod MIN_UZORAK odluka po tipu se ne tvrdi nista. Upotreba: python tools/odluke_izvjestaj.py"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import odluke  # noqa: E402
from core.verifier import OZNAKA_TEZKI_TIPOVI  # noqa: E402

CKB = Path("/storage/emulated/0/booklyfi_checkpoints")
MIN_UZORAK = 10
CILJ = 0.70  # prag iz TASKS (P2.5.3): preciznost > 70%


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - r), min(1.0, c + r))


def redovi(p):
    d = json.loads(p.read_text("utf-8"))
    if isinstance(d, dict):
        for k in ("blokovi", "rezultati", "redovi", "items"):
            if isinstance(d.get(k), list):
                return [x for x in d[k] if isinstance(x, dict)]
        return [v for v in d.values() if isinstance(v, dict)]
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def teske_po_knjizi():
    out = {}
    for p in sorted(CKB.glob("_skr_*/checkpoints/quality_verifier.json")):
        ime = p.parent.parent.name[5:][:30]
        try:
            n = sum(1 for v in redovi(p) for g in (v.get("greske") or [])
                    if g.get("tip") in OZNAKA_TEZKI_TIPOVI)
        except Exception as e:
            print(f"  (ne mogu citati {p.parent.parent.name[:30]}: {e!r})")
            continue
        out[ime] = n
    return out


def main():
    st = odluke.statistika()
    print("=== Preciznost teskih gresaka (iz odluka) ===")
    uk_p = uk_o = 0
    for tip in sorted(st):
        d = st[tip]
        p, o = d["prevedi_ponovo"], d["ostavi"]
        n = p + o
        uk_p += p
        uk_o += o
        if n < MIN_UZORAK:
            print(f"  {tip:14s} n={n:3d}  premalo uzoraka (treba >= {MIN_UZORAK}); do sada {p} stvarnih / {o} laznih")
        else:
            lo, hi = wilson(p, n)
            print(f"  {tip:14s} n={n:3d}  preciznost {p/n:.0%} (raspon {lo:.0%}-{hi:.0%})")
    n = uk_p + uk_o
    if n < MIN_UZORAK:
        print(f"  UKUPNO         n={n:3d}  premalo uzoraka; nema pouzdane brojke")
    else:
        lo, hi = wilson(uk_p, n)
        v = "IZNAD cilja" if lo > CILJ else ("ISPOD cilja" if hi < CILJ else "neodlucivo (raspon obuhvaca cilj)")
        print(f"  UKUPNO         n={n:3d}  preciznost {uk_p/n:.0%} (raspon {lo:.0%}-{hi:.0%}); cilj {CILJ:.0%}: {v}")

    print("\n=== Po knjizi: odluke vs teski nalazi ===")
    odl = Counter(z.get("knjiga", "?") for z in odluke._stanje().values())
    tez = teske_po_knjizi()
    for k in sorted(set(odl) | set(tez)):
        t = tez.get(k)
        cekaju = "?" if t is None else max(0, t - odl.get(k, 0))
        print(f"  {k:30s} teskih nalaza {t if t is not None else '?':>3}  odluceno {odl.get(k, 0):>3}  ceka ~{cekaju}")
    ukupno = sum(tez.values())
    print(f"\n  Ukupno teskih nalaza u svim knjigama: {ukupno}; odluceno: {sum(odl.values())}")
    potrebno = max(0, MIN_UZORAK * 2 - n)
    print(f"  Za brojku po tipu treba jos oko {potrebno} odluka (cilj: {MIN_UZORAK}+ po tipu).")
    print("  Izvor novih kartica: verifikator na novoj knjizi normalne proze (AI pozivi), pa /revizija.")


if __name__ == "__main__":
    main()
