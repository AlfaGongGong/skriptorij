"""P2.5.2: dry-run AI arbitra nad kriv_smisao nalazima verifikatora.

NE mijenja .chk ni EPUB. Pise TSV prijedloga i usporedbu sa zlatnim setom.
Upotreba: python tools/arbitar_run.py <knjiga.epub> <ime_skr> <gold_prefix> [max_poziva]
primjer:  python tools/arbitar_run.py Delacroix.epub Delacroix Delacroix 0
"""
import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import arbitar as A  # noqa: E402

CKB = Path("/storage/emulated/0/booklyfi_checkpoints")
DL = Path("/storage/emulated/0/Download")
SYS = "Odgovaras iskljucivo valjanim JSON objektom, bez dodatnog teksta."
PRED = {"stvarna_greska": "stvarna", "lazni_alarm": "lazni", "nesigurno": "sumnjivo"}


def ucitaj_nalaze(ck):
    """Isti redoslijed i numeracija kao ispis kriv_smisao_svi_*.md."""
    d = json.load(open(ck / "quality_verifier.json", encoding="utf-8"))
    out, br = [], 0
    for k, v in sorted(d.items()):
        if v.get("verifier") == "skip":
            continue
        for g in (v.get("greske") or []):
            if g.get("tip") != "kriv_smisao":
                continue
            br += 1
            out.append({"br": br, "blok": k, "score": v.get("score"), "g": g})
    return out


def raw_bloka(ck, k):
    p = ck / (k if k.endswith(".chk") else k + ".chk")
    return p.read_text("utf-8", "ignore") if p.exists() else ""


def cist(s):
    return str(s or "").replace("\t", " ").replace("\n", " ").strip()


async def jedan(engine, sem, n, rj, ck, maxp, brojac):
    g = n["g"]
    hr = (g.get("hr_fragment") or "").strip()
    raw = raw_bloka(ck, n["blok"])
    res = {"br": n["br"], "blok": n["blok"], "en": g.get("en_fragment") or "", "hr": hr,
           "izvor": "ai", "presuda": "", "zamjena": "", "razlog": "", "sigurna": "", "nadjen": ""}
    ok, razlog = A.predfilter(g)
    if not ok:
        res.update(izvor="predfilter", presuda="lazni_alarm", razlog=razlog)
        return res
    if maxp and brojac[0] >= maxp:
        res.update(izvor="preskoceno", presuda="?", razlog="max_poziva")
        return res
    brojac[0] += 1
    prompt = A.napravi_prompt(g.get("en_fragment"), hr, g.get("objasnjenje"),
                              A.kontekst_oko(A._plain(raw), hr))
    try:
        async with sem:
            r = await engine._call_ai_engine(prompt, n["br"], uloga="VERIFIER", filename=n["blok"],
                                             sys_override=SYS, tip_bloka="naracija")
        txt = r[0] if isinstance(r, (tuple, list)) and r else r
        d = A.parsiraj_odgovor(txt if isinstance(txt, str) else "")
    except Exception as e:
        res.update(presuda="?", razlog="greska:" + type(e).__name__ + ":" + str(e)[:80])
        return res
    if not d:
        res.update(presuda="?", razlog="neparsirano:" + cist(txt)[:80])
        return res
    res.update(presuda=d["presuda"], zamjena=d["zamjena"], razlog=d["razlog"])
    if d["presuda"] == "stvarna_greska":
        s_ok, s_r = A.provjeri_zamjenu(hr, d["zamjena"], rj)
        res["sigurna"] = "da" if s_ok else "ne:" + s_r
        res["nadjen"] = "da" if A.nadji_u_raw(raw, hr) is not None else "ne"
    return res


async def main(epub, ime_skr, prefix, maxp):
    from core.engine import SkriptorijAllInOne
    engine = SkriptorijAllInOne(epub, "V10_TURBO", {}, {})
    ck = CKB / ("_skr_" + ime_skr) / "checkpoints"
    if Path(engine.work_dir).resolve() != ck.parent.resolve():
        print("STOP: engine work_dir =", engine.work_dir, "| ocekivano", ck.parent)
        return 2
    nalazi = ucitaj_nalaze(ck)
    rj = A.rijecnik_knjige(ck)
    print("nalaza kriv_smisao:", len(nalazi), "| rijecnik:", len(rj), "rijeci")
    sem = asyncio.Semaphore(3)
    brojac = [0]
    t0 = time.time()
    rez = await asyncio.gather(*[jedan(engine, sem, n, rj, ck, maxp, brojac) for n in nalazi])
    print("AI poziva: %d | trajanje %.0f s" % (brojac[0], time.time() - t0))

    gold = json.load(open(Path(__file__).resolve().parent.parent / "data/arbitar_zlatni_set.json",
                          encoding="utf-8"))["presude"]
    tsv = DL / ("arbitar_dryrun_%s_%s.tsv" % (prefix, os.environ.get("TS", "x")))
    kol = ["br", "gold", "pred", "izvor", "presuda", "sigurna", "nadjen", "en", "hr", "zamjena", "razlog", "blok"]
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("\t".join(kol) + "\n")
        for r in rez:
            r["gold"] = gold.get("%s.%d" % (prefix, r["br"]), "?")
            r["pred"] = PRED.get(r["presuda"], "?")
            f.write("\t".join(cist(r.get(c)) for c in kol) + "\n")
    print("TSV:", tsv)

    m = Counter((r["gold"], r["pred"]) for r in rez)
    print("\n== zlatni (red) x arbitar (stupac) ==")
    stup = ["stvarna", "sumnjivo", "lazni", "?"]
    print("%-10s" % "" + "".join("%10s" % s for s in stup))
    for gl in ("stvarna", "sumnjivo", "lazni"):
        print("%-10s" % gl + "".join("%10d" % m[(gl, s)] for s in stup))
    gs = sum(1 for r in rez if r["gold"] == "stvarna")
    ps = [r for r in rez if r["pred"] == "stvarna"]
    pogodak = sum(1 for r in ps if r["gold"] == "stvarna")
    opasni = [r for r in ps if r["gold"] == "lazni"]
    prim = [r for r in ps if r["sigurna"] == "da" and r["nadjen"] == "da"]
    prim_opasni = [r for r in prim if r["gold"] == "lazni"]
    print("\nzlatnih stvarnih: %d | arbitar kaze stvarna: %d | od toga pogodak: %d" % (gs, len(ps), pogodak))
    print("recall stvarnih: %.0f%% | preciznost: %.0f%%" % (
        100.0 * pogodak / gs if gs else 0, 100.0 * pogodak / len(ps) if ps else 0))
    print("OPASNI (arbitar: stvarna, zlatni: lazni): %d" % len(opasni))
    print("zamjena primjenjiva (sigurna + fragment 1x): %d | od toga opasnih: %d" % (len(prim), len(prim_opasni)))
    print("razlozi odbijene zamjene:", dict(Counter(r["sigurna"] for r in ps if r["sigurna"] != "da")))
    print("\n== primjenjive zamjene (staro -> novo) ==")
    for r in prim:
        print("  #%d [%s] %s -> %s" % (r["br"], r["gold"], r["hr"][:45], r["zamjena"][:45]))
    print("\n== OPASNI ==")
    for r in opasni:
        print("  #%d %s | %s | %s" % (r["br"], r["hr"][:40], r["zamjena"][:40], r["razlog"][:80]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    mx = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    rc = asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3], mx))
    sys.stdout.flush()
    os._exit(rc)
