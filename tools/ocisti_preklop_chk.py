"""Ciscenje preklopa u postojecim .chk (osnovni i .lektura). Upotreba: ocisti_preklop_chk.py CK BACKUP_DIR [--primijeni]"""
import os, pathlib, re, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.preklop import skini_preklop

ck, bk = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
primijeni = "--primijeni" in sys.argv
ukupno = 0
for d in sorted(ck.glob("_skr_*")):
    cdir = d / "checkpoints"
    if not cdir.is_dir():
        continue
    for suf, rx in (("", r"^(.*)_blok_(\d+)\.chk$"), (".lektura", r"^(.*)_blok_(\d+)\.lektura\.chk$")):
        grupe = {}
        for f in cdir.iterdir():
            m = re.match(rx, f.name)
            if m:
                grupe.setdefault(m.group(1), {})[int(m.group(2))] = f
        par = fix = odl = 0
        for base, mp in grupe.items():
            for i in sorted(mp):
                if i - 1 not in mp:
                    continue
                par += 1
                prev = mp[i - 1].read_text("utf-8", "ignore")
                cur = mp[i].read_text("utf-8", "ignore")
                novo, n = skini_preklop(prev, cur)
                if n:
                    fix += 1; odl += n
                    print(f"  {d.name[:30]} {mp[i].name}: -{n}")
                    if primijeni:
                        dst = bk / "chk" / d.name / "checkpoints" / mp[i].name
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(mp[i], dst)
                        tmp = mp[i].with_suffix(".tmp_preklop")
                        tmp.write_text(novo, "utf-8")
                        os.replace(tmp, mp[i])
        print(f"{d.name[:40]} [{suf or 'osnovni'}]: parova {par}, blokova ispravljeno {fix}, odlomaka uklonjeno {odl}")
        ukupno += fix
print(f"UKUPNO ispravljenih blokova: {ukupno}")
