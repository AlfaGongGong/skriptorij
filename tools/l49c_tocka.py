# -*- coding: utf-8 -*-
"""tools/l49c_tocka.py - L49c: tockasti popravak (L49b) nad vec spremljenim blokovima s nalazima.

Upotreba: python tools/l49c_tocka.py [dio_imena_knjige=Carter] [max_blokova=30]
Backup quality_verifier.json u .logs; .chk se mijenja samo kad je gresaka manje
(original ide u checkpoints/verifier_prije/*.tocka.txt). Env L49C_PONOVI=1 ponavlja i vec probane.
"""
import asyncio
import json
import os
import re
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
FRAG = (sys.argv[1] if len(sys.argv) > 1 else "Carter").lower()
MAXB = int(sys.argv[2]) if len(sys.argv) > 2 else 30
PONOVI = os.environ.get("L49C_PONOVI") == "1"


def stat(db):
    c = Counter(v.get("oznaka") for v in db.values())
    g = sum(len(v.get("greske") or []) for v in db.values() if v.get("verifier") == "flags")
    return dict(c), g


async def main():
    from config.settings import CHECKPOINT_BASE_DIR, INPUT_DIR
    from core.engine import SkriptorijAllInOne
    from processing.verifier_tocka import kandidati, tocka_popravak

    cands = []
    for q in Path(CHECKPOINT_BASE_DIR).glob("_skr_*/checkpoints/quality_verifier.json"):
        skr = q.parent.parent
        if FRAG not in skr.name.lower():
            continue
        try:
            d = json.loads(q.read_text("utf-8"))
        except Exception:
            continue
        cands.append((sum(1 for v in d.values() if v.get("verifier") == "flags"), skr, q))
    cands.sort(key=lambda x: -x[0])
    for n, s, _ in cands:
        print(">> skr kandidat: %s (flags=%d)" % (s.name[:70], n))
    if not cands:
        print(">> STOP: nema _skr_ foldera s '%s'" % FRAG)
        return 2
    _, SKR, QV = cands[0]

    roots = [Path(INPUT_DIR), Path("/storage/emulated/0/Books"), Path("/storage/emulated/0/Download")]
    epubi = []
    for r in roots:
        if r.exists():
            for p in r.rglob("*.epub"):
                nm = p.name.upper()
                if FRAG in p.name.lower() and "PREVEDENO" not in nm and "STYLED" not in nm:
                    epubi.append(p)
    eng, SRC = None, None
    for p in epubi:
        try:
            e = SkriptorijAllInOne(str(p), "V10_TURBO", {}, {})
        except Exception as ex:
            print(">> engine pad za %s: %r" % (p.name[:50], ex))
            continue
        if Path(e.work_dir).resolve() == SKR.resolve():
            eng, SRC = e, p
            break
    if eng is None:
        print(">> STOP: nijedan izvorni EPUB ne daje work_dir == %s; probani: %s" % (
            SKR.name[:60], [p.name[:50] for p in epubi]))
        return 2
    print(">> epub:", SRC.name[:80])

    CK = SKR / "checkpoints"
    bk = ROOT / ".logs" / ("l49c_bk_" + time.strftime("%Y%m%d_%H%M%S"))
    bk.mkdir(parents=True, exist_ok=True)
    shutil.copy2(QV, bk / "quality_verifier.json")
    print(">> backup:", bk)

    db0 = json.loads(QV.read_text("utf-8"))
    print(">> PRIJE oznake/greske u flags blokovima:", stat(db0))

    jobs, bez_kand, vec_probano = [], 0, 0
    for key, v in db0.items():
        if v.get("verifier") != "flags":
            continue
        m = re.match(r"(.+)_blok_(\d+)$", key)
        if not m:
            continue
        if not kandidati(v.get("greske")):
            bez_kand += 1
            continue
        if "tocka" in v and not PONOVI:
            vec_probano += 1
            continue
        jobs.append((v.get("score") if isinstance(v.get("score"), (int, float)) else 9, key, m.group(1), int(m.group(2))))
    jobs.sort()
    print(">> blokova s nalazima: bez kandidata (izostavljeno/dodano): %d | vec probano: %d | za obradu: %d (max %d)" % (
        bez_kand, vec_probano, len(jobs), MAXB))
    jobs = jobs[:MAXB]

    z = zipfile.ZipFile(SRC)
    en_files = {n.rsplit("/", 1)[-1]: n for n in z.namelist() if n.lower().endswith((".html", ".xhtml"))}
    en_cache = {}

    def en_chunks(fn):
        if fn not in en_cache:
            if fn not in en_files:
                en_cache[fn] = None
            else:
                ch = eng.chunk_html(z.read(en_files[fn]).decode("utf-8", "ignore"))
                ch = [c if isinstance(c, str) else (c[0] if isinstance(c, (tuple, list)) else str(c)) for c in ch]
                n_hr = len([p for p in CK.glob(fn + "_blok_*.chk") if re.search(r"_blok_\d+\.chk$", p.name)])
                en_cache[fn] = ch if len(ch) == n_hr else None
        return en_cache[fn]

    sem = asyncio.Semaphore(3)
    t0 = time.time()
    gotovo = [0]
    preskoc = []

    async def jedan(score, key, fn, idx):
        ch = en_chunks(fn)
        if not ch or idx >= len(ch):
            preskoc.append(key + " (EN/HR broj blokova se ne slaze)")
            return
        async with sem:
            try:
                await tocka_popravak(eng, db0[key], ch[idx], key, idx, fn, "naracija", {})
            except Exception as ex:
                preskoc.append("%s greska %r" % (key, ex))
        gotovo[0] += 1
        if gotovo[0] % 5 == 0 or gotovo[0] == len(jobs):
            print("  %d/%d (%.0f s)" % (gotovo[0], len(jobs), time.time() - t0), flush=True)

    await asyncio.gather(*[jedan(*j) for j in jobs])

    db1 = json.loads(QV.read_text("utf-8"))
    print(">> POSLIJE oznake/greske u flags blokovima:", stat(db1))
    pop, razlozi, ns, nn = 0, Counter(), 0, 0
    for _, key, _, _ in jobs:
        t = (db1.get(key) or {}).get("tocka")
        if not t:
            razlozi["bez_zapisa"] += 1
        elif t.get("popravljeno"):
            pop += 1
            ns += t.get("n_prije") or 0
            nn += t.get("n_poslije") or 0
        else:
            razlozi[t.get("razlog") or ("vec_ispravno" if t.get("vec_ispravno") else "preskoceno")] += 1
    print(">> blokova popravljeno: %d od %d | greske u popravljenima %d -> %d" % (pop, len(jobs), ns, nn))
    print(">> nepopravljeni po razlogu:", dict(razlozi))
    for _, key, _, _ in jobs:
        t = (db1.get(key) or {}).get("tocka") or {}
        for im in (t.get("izmjene") or [])[:3]:
            print("   IZMJENA %s [%s]: %r -> %r" % (key[-24:], im.get("tip"), im.get("prije", "")[:70], im.get("poslije", "")[:70]))
    for s in preskoc[:10]:
        print("   PRESKOCENO:", s)
    return 0


rc = asyncio.run(main())
sys.stdout.flush()
os._exit(rc)
