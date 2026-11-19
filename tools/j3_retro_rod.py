"""J3: retro korekcija roda pripovjedaca u postojecim .chk (isti korak kao _prip_korak).
Suhi prolaz je zadan; J3_PRIMIJENI=1 stvarno pise (uz backup u .logs/j3_bk_*).
Upotreba: python3 tools/j3_retro_rod.py [dio_imena_knjige]"""
import difflib
import os
import re
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processing import pipeline as P  # noqa: E402

PRIMIJENI = os.environ.get("J3_PRIMIJENI") == "1"
KORIJENI = [
    "/storage/emulated/0/booklyfi_checkpoints",
    "/root/Skriptorij/data",
    "/root/skriptorij/data",
]
if os.environ.get("J3_KORIJENI"):
    KORIJENI = os.environ["J3_KORIJENI"].split(":")
RX = re.compile(r"^(.*)_blok_(\d+)\.chk$")
TAG = re.compile(r"<[^>]*>")
BK = Path(".logs") / ("j3_bk_" + time.strftime("%Y%m%d_%H%M%S"))
filt = sys.argv[1].lower() if len(sys.argv) > 1 else ""


def rijeci_razlika(a, b):
    ra, rb = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ra, rb).get_opcodes():
        if op != "equal":
            out.append(" ".join(ra[i1:i2]) + " -> " + " ".join(rb[j1:j2]))
    return out


def obradi_mapu(d):
    zast = []
    eng = SimpleNamespace(log=lambda *a, **k: None, checkpoint_dir=d)
    P._hr_oznaci = lambda self, f, i, razlog, *a, **k: zast.append((f, i, razlog))
    grupe = {}
    for p in d.glob("*.chk"):
        m = RX.match(p.name)
        if m and not p.name.endswith(".prevod.chk"):
            grupe.setdefault(m.group(1), {})[int(m.group(2))] = p
    ukupno = {"blokova": 0, "promijenjeno": 0, "zamjena": 0, "preskoceno": 0}
    uzorci = []
    for fn in sorted(grupe):
        for idx in sorted(grupe[fn]):
            p = grupe[fn][idx]
            t = p.read_text("utf-8", errors="ignore")
            ukupno["blokova"] += 1
            if "NEPREVEDENO" in t or len(t.strip()) < 10:
                ukupno["preskoceno"] += 1
                continue
            n = P._prip_korak(eng, t, fn, idx)
            if n == t:
                continue
            if TAG.findall(n) != TAG.findall(t) or abs(len(n) - len(t)) > 0.05 * len(t) + 20:
                ukupno["preskoceno"] += 1
                continue
            raz = rijeci_razlika(t, n)
            ukupno["promijenjeno"] += 1
            ukupno["zamjena"] += len(raz)
            if len(uzorci) < 6:
                uzorci.append((p.name, raz[:4]))
            if PRIMIJENI:
                (BK / d.name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, BK / d.name / p.name)
                tmp = p.with_suffix(".chk.tmp")
                tmp.write_text(n, "utf-8")
                os.replace(tmp, p)
    return ukupno, uzorci, zast


def main():
    print("=== J3 " + ("PRIMJENA" if PRIMIJENI else "SUHI PROLAZ") + " ===")
    vidjeno = set()
    for k in KORIJENI:
        kp = Path(k)
        if not kp.is_dir():
            continue
        for d in sorted(kp.glob("_skr_*")):
            r = d.resolve()
            if r in vidjeno or not d.is_dir() or (filt and filt not in d.name.lower()):
                continue
            vidjeno.add(r)
            if not any(d.glob("*.chk")):
                continue
            u, uz, z = obradi_mapu(d)
            print(f">> {d.name[:60]} | blokova {u['blokova']} | promijenjeno {u['promijenjeno']} | zamjena {u['zamjena']} | preskoceno {u['preskoceno']} | za provjeru {len(z)}")
            for ime, raz in uz:
                print(f"   {ime}: {raz}")
            for f, i, razlog in z[:5]:
                print(f"   ? {f}_blok_{i}: {razlog[:70]}")
    if PRIMIJENI:
        print("backup:", BK)
    print("=== J3 KRAJ ===")


if __name__ == "__main__":
    main()
