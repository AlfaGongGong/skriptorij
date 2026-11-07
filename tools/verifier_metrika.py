"""Metrika verifikatora iz postojecih quality_verifier.json (bez novog runa).
Oznaka se RACUNA ponovo iz 'greske' po trenutnoj oznaka_bloka(), ne cita se spremljena.
Upotreba: python tools/verifier_metrika.py [ime_dijela_foldera ...]"""
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.verifier import OZNAKA_TEZKI_TIPOVI, oznaka_bloka  # noqa: E402

CKB = "/storage/emulated/0/booklyfi_checkpoints"


def hr_rijeci(ck: Path) -> int:
    n = 0
    for p in ck.glob("*.chk"):
        t = re.sub(r"<!--.*?-->", " ", p.read_text("utf-8", "ignore"), flags=re.S)
        n += len(re.sub(r"<[^>]+>", " ", t).split())
    return n


def izracunaj(redovi, rijeci):
    ozn = Counter()
    tezi = pregled = 0
    for v in redovi:
        g = v.get("greske") or []
        ozn[oznaka_bloka({"provjeren": True, "greske": g})] += 1
        for x in g:
            if x.get("tip") in OZNAKA_TEZKI_TIPOVI:
                tezi += 1
            else:
                pregled += 1
    k = 1000.0 / rijeci if rijeci else 0.0
    return {"blokova": len(redovi), "oznake": dict(ozn), "tezke": tezi, "za_pregled": pregled,
            "tezke_na_1000": round(tezi * k, 2), "pregled_na_1000": round(pregled * k, 2), "rijeci": rijeci}


def main(filtri):
    for f in sorted(glob.glob(CKB + "/_skr_*/checkpoints/quality_verifier.json")):
        ime = f.split("/_skr_")[1].split("/")[0]
        if ime.startswith(("Unbound", "The_Wisdom")):
            continue
        if filtri and not any(x.lower() in ime.lower() for x in filtri):
            continue
        d = json.load(open(f, encoding="utf-8"))
        red = [v for v in d.values() if v.get("oznaka") != "neprovjeren" and v.get("verifier") != "skip"]
        if not red:
            continue
        r = izracunaj(red, hr_rijeci(Path(f).parent))
        print("%-30s blokova %d | %s" % (ime[:30], r["blokova"], r["oznake"]))
        print("   teske: %d (%.2f/1000 rijeci) | za pregled (kriv_smisao..): %d (%.2f/1000) | rijeci %d"
              % (r["tezke"], r["tezke_na_1000"], r["za_pregled"], r["pregled_na_1000"], r["rijeci"]))


if __name__ == "__main__":
    main(sys.argv[1:])
