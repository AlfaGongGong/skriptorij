import asyncio, json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
os.chdir("/root/skriptorij")
SRC, SKR = sys.argv[1], Path(sys.argv[2])
CK = SKR / "checkpoints"
QV = CK / "quality_verifier.json"

async def main():
    from core.engine import SkriptorijAllInOne
    from core.verifier import oznaka_bloka, provjeri_blok_async
    from processing.verifier_hook import sazetak
    import zipfile
    eng = SkriptorijAllInOne(SRC, "V10_TURBO", {}, {})
    if Path(eng.work_dir).resolve() != SKR.resolve():
        print("STOP: work_dir", eng.work_dir, "!= ocekivano", SKR); return 2
    z = zipfile.ZipFile(SRC)
    en_files = {n.rsplit("/", 1)[-1]: n for n in z.namelist() if re.search(r"dummy_split_\d+\.html$", n)}
    res_db = {}
    if QV.exists():
        try: res_db = json.loads(QV.read_text("utf-8"))
        except Exception: res_db = {}
    poslovi, preskoceno = [], []
    for fn in sorted(en_files):
        hr_blokovi = sorted(
            [p for p in CK.glob(fn + "_blok_*.chk") if re.search(r"_blok_\d+\.chk$", p.name)],
            key=lambda p: int(re.search(r"_blok_(\d+)\.chk$", p.name).group(1)))
        if not hr_blokovi: continue
        en_html = z.read(en_files[fn]).decode("utf-8", "ignore")
        chunks = eng.chunk_html(en_html)
        chunks = [c if isinstance(c, str) else (c[0] if isinstance(c, (tuple, list)) else str(c)) for c in chunks]
        if len(chunks) != len(hr_blokovi):
            preskoceno.append("%s EN=%d HR=%d" % (fn, len(chunks), len(hr_blokovi))); continue
        for i, p in enumerate(hr_blokovi):
            idx = int(re.search(r"_blok_(\d+)\.chk$", p.name).group(1))
            key = "%s_blok_%d" % (fn, idx)
            if key in res_db and res_db[key].get("verifier") != "skip": continue
            hr = re.sub(r"^<!--.*?-->\s*", "", p.read_text("utf-8", "ignore"), flags=re.S)
            poslovi.append((key, fn, idx, chunks[i], hr))
    print("za verificirati: %d | vec gotovo: %d | preskoceno datoteka: %d" % (len(poslovi), len(res_db), len(preskoceno)))
    for s in preskoceno: print("  PRESKOCENO:", s)
    sem = asyncio.Semaphore(3); lock = asyncio.Lock(); gotovo = [0]; t0 = time.time()
    async def jedan(key, fn, idx, en, hr):
        async with sem:
            zadnji = {}
            async def _fleet(prompt, sys_p):
                r = await eng._call_ai_engine(prompt, idx, uloga="VERIFIER", filename=fn, sys_override=sys_p, tip_bloka="naracija")
                zadnji["r"] = r; return r
            try:
                res = await provjeri_blok_async(en, hr, {}, fleet=_fleet)
                out = sazetak(res)
                if out.get("verifier") == "skip":
                    r = zadnji.get("r"); raw = r[0] if isinstance(r, (tuple, list)) and r else r
                    raw = raw if isinstance(raw, str) else ""
                    out["raw_len"] = len(raw); out["raw_tail"] = raw[-160:]
                zap = dict(out, oznaka=oznaka_bloka(res))
            except Exception as e:
                zap = {"verifier": "skip", "status": "greska", "error": repr(e)[:150], "oznaka": "neprovjeren"}
        async with lock:
            res_db[key] = zap
            tmp = QV.with_name("quality_verifier.json.tmp")
            tmp.write_text(json.dumps(res_db, ensure_ascii=False, indent=2), "utf-8"); os.replace(tmp, QV)
            gotovo[0] += 1
            if gotovo[0] % 10 == 0 or gotovo[0] == len(poslovi):
                print("  %d/%d (%.0f s)" % (gotovo[0], len(poslovi), time.time() - t0), flush=True)
    await asyncio.gather(*[jedan(*j) for j in poslovi])
    from collections import Counter
    c = Counter(v.get("oznaka") for v in res_db.values())
    print("OZNAKE:", dict(c))
    return 0

rc = asyncio.run(main())
sys.stdout.flush(); os._exit(rc)
