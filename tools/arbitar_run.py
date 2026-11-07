"""P2.5.2b: SLIJEPI dry-run AI arbitra nad kriv_smisao nalazima verifikatora.

Arbitar NE vidi tvrdnju verifikatora. Tri prolaza: slijepa presuda, zamjena (samo za 'razlicito'),
provjera zamjene (vjernija? izmisljene rijeci?). NE mijenja .chk ni EPUB.
Upotreba: python tools/arbitar_run.py <knjiga.epub> <ime_skr> <gold_prefix> [max_poziva]
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
MAP = {"ekvivalentno": "lazni", "razlicito": "stvarna", "nesigurno": "sumnjivo"}


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


EN_TEXT = {}


def ucitaj_en(epub):
    """Jednom ucita EN tekst svih Text/*.html iz izvornog EPUB-a (naziv_fajla -> plain tekst)."""
    import zipfile
    EN_TEXT.clear()
    with zipfile.ZipFile(epub) as z:
        for nm in z.namelist():
            if nm.endswith((".html", ".xhtml")) and "/Text/" in nm:
                EN_TEXT[nm.rsplit("/", 1)[1]] = A._plain(z.read(nm).decode("utf-8", "ignore"))
    print("EN tekstova ucitano:", len(EN_TEXT))


def nadji_en(ck, blok, en, n=500):
    """EN odlomak oko en_fragmenta iz izvornih OEBPS/Text/*.html u _skr_ folderu ("" ako nije nadjen)."""
    import re
    frag = re.sub(r"\s+", " ", (en or "").strip())
    if len(frag) < 6:
        return ""
    if not EN_TEXT:
        return ""
    prvi = blok.split(".html_blok")[0] + ".html"
    kandidati = ([prvi] if prvi in EN_TEXT else []) + [k for k in sorted(EN_TEXT) if k != prvi]
    for k in kandidati:
        t = EN_TEXT[k]
        for f in (frag, frag.replace("\u2019", "'"), frag.replace("'", "\u2019")):
            i = t.find(f)
            if i >= 0:
                return t[max(0, i - n): i + len(f) + n]
    return ""


def cist(s):
    return str(s or "").replace("\t", " ").replace("\n", " ").strip()


async def zovi(engine, sem, prompt, br, blok):
    async with sem:
        r = await engine._call_ai_engine(prompt, br, uloga="VERIFIER", filename=blok,
                                         sys_override=SYS, tip_bloka="naracija")
    txt = r[0] if isinstance(r, (tuple, list)) and r else r
    return txt if isinstance(txt, str) else ""


async def jedan(engine, sem, n, ck, maxp, brojac):
    g = n["g"]
    en = g.get("en_fragment") or ""
    hr = (g.get("hr_fragment") or "").strip()
    raw = raw_bloka(ck, n["blok"])
    res = {"br": n["br"], "blok": n["blok"], "en": en, "hr": hr, "izvor": "ai",
           "presuda": "?", "smisao": "", "zamjena": "", "razlog": "", "sigurna": "", "nadjen": ""}
    ok, razlog = A.predfilter(g)
    if not ok:
        res.update(izvor="predfilter", presuda="lazni", razlog=razlog)
        return res
    if maxp and brojac[0] >= maxp:
        res.update(izvor="preskoceno", razlog="max_poziva")
        return res
    brojac[0] += 1
    ctx = A.kontekst_oko(A._plain(raw), hr)
    enc = nadji_en(ck, n["blok"], en)
    res["en_ctx"] = "da" if enc else "ne"
    try:
        t1 = await zovi(engine, sem, A.prompt_slijepo_en(en, hr, ctx, enc), n["br"], n["blok"])
        d1 = A.parsiraj_slijepo(t1)
        if not d1:
            res["razlog"] = "neparsirano:" + cist(t1)[:80]
            return res
        res.update(presuda=MAP[d1["presuda"]], smisao=d1["moj_smisao"], razlog=d1["razlog"])
        if d1["presuda"] != "razlicito":
            return res
        res["nadjen"] = "da" if A.nadji_u_raw(raw, hr) is not None else "ne"
        t2 = await zovi(engine, sem, A.prompt_zamjena(en, hr, ctx, d1["moj_smisao"]), n["br"], n["blok"])
        d2 = A.parsiraj_zamjena(t2)
        if not d2 or not d2["zamjena"]:
            res["sigurna"] = "ne:bez_zamjene"
            return res
        res["zamjena"] = d2["zamjena"]
        s_ok, s_r = A.provjeri_zamjenu(hr, d2["zamjena"], None)
        if not s_ok:
            res["sigurna"] = "ne:" + s_r
            return res
        t3 = await zovi(engine, sem, A.prompt_provjera(en, hr, d2["zamjena"]), n["br"], n["blok"])
        d3 = A.parsiraj_provjera(t3)
        if not d3:
            res["sigurna"] = "ne:provjera_neparsirana"
        elif not d3["vjernije"]:
            res["sigurna"] = "ne:nije_vjernije"
        elif d3["izmisljene"]:
            res["sigurna"] = "ne:izmisljene:" + ",".join(d3["izmisljene"][:3])
        else:
            res["sigurna"] = "da"
    except Exception as e:
        res["razlog"] = "greska:" + type(e).__name__ + ":" + str(e)[:80]
    return res


async def main(epub, ime_skr, prefix, maxp):
    from core.engine import SkriptorijAllInOne
    engine = SkriptorijAllInOne(epub, "V10_TURBO", {}, {})
    ucitaj_en(epub)
    ck = CKB / ("_skr_" + ime_skr) / "checkpoints"
    if Path(engine.work_dir).resolve() != ck.parent.resolve():
        print("STOP: engine work_dir =", engine.work_dir, "| ocekivano", ck.parent)
        return 2
    nalazi = ucitaj_nalaze(ck)
    print("nalaza kriv_smisao:", len(nalazi))
    sem = asyncio.Semaphore(3)
    brojac = [0]
    t0 = time.time()
    rez = await asyncio.gather(*[jedan(engine, sem, n, ck, maxp, brojac) for n in nalazi])
    print("slijepih presuda (AI): %d | trajanje %.0f s" % (brojac[0], time.time() - t0))
    print("EN kontekst nadjen: %d/%d" % (sum(1 for x in rez if x.get("en_ctx") == "da"), sum(1 for x in rez if x.get("en_ctx"))))

    gold = json.load(open(Path(__file__).resolve().parent.parent / "data/arbitar_zlatni_set.json",
                          encoding="utf-8"))["presude"]
    tsv = DL / ("arbitar_slijepi_%s_%s.tsv" % (prefix, os.environ.get("TS", "x")))
    kol = ["br", "gold", "presuda", "izvor", "sigurna", "nadjen", "en", "hr", "zamjena", "smisao", "razlog", "blok"]
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("\t".join(kol) + "\n")
        for r in rez:
            r["gold"] = gold.get("%s.%d" % (prefix, r["br"]), "?")
            f.write("\t".join(cist(r.get(c)) for c in kol) + "\n")
    print("TSV:", tsv)

    m = Counter((r["gold"], r["presuda"]) for r in rez)
    stup = ["stvarna", "sumnjivo", "lazni", "?"]
    print("\n== zlatni (red) x arbitar (stupac) ==")
    print("%-10s" % "" + "".join("%10s" % s for s in stup))
    for gl in ("stvarna", "sumnjivo", "lazni"):
        print("%-10s" % gl + "".join("%10d" % m[(gl, s)] for s in stup))
    gs = sum(1 for r in rez if r["gold"] == "stvarna")
    ps = [r for r in rez if r["presuda"] == "stvarna"]
    pog = sum(1 for r in ps if r["gold"] == "stvarna")
    opasni = [r for r in ps if r["gold"] == "lazni"]
    prim = [r for r in ps if r["sigurna"] == "da" and r["nadjen"] == "da"]
    prim_op = [r for r in prim if r["gold"] == "lazni"]
    print("\nzlatnih stvarnih: %d | arbitar kaze stvarna: %d | pogodak: %d" % (gs, len(ps), pog))
    print("recall: %.0f%% | preciznost: %.0f%% (prosli put 95%% / 42%%)" % (
        100.0 * pog / gs if gs else 0, 100.0 * pog / len(ps) if ps else 0))
    print("OPASNI (arbitar stvarna, zlatni lazni): %d | primjenjivih zamjena: %d | od toga opasnih: %d" % (
        len(opasni), len(prim), len(prim_op)))
    print("odbijene zamjene:", dict(Counter(r["sigurna"].split(":")[0] + ":" + (r["sigurna"].split(":")[1] if ":" in r["sigurna"] else "")
                                         for r in ps if r["sigurna"] != "da")))
    print("\n== primjenjive zamjene (staro -> novo) ==")
    for r in prim:
        print("  #%d [%s] %s -> %s" % (r["br"], r["gold"], r["hr"][:45], r["zamjena"][:45]))
    print("\n== OPASNI ==")
    for r in opasni:
        print("  #%d %s | %s | %s" % (r["br"], r["hr"][:35], r["zamjena"][:35], r["razlog"][:70]))
    print("\n== propusteni (zlatni stvarna, arbitar nije) ==")
    for r in rez:
        if r["gold"] == "stvarna" and r["presuda"] != "stvarna":
            print("  #%d [%s] %s | %s" % (r["br"], r["presuda"], r["hr"][:40], r["razlog"][:70]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    mx = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    rc = asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3], mx))
    sys.stdout.flush()
    os._exit(rc)
