"""P2.15: offline classla provjera .chk blokova. Trazi recenice s nizom tokena UPOS 'X' (strani tekst).
Upotreba: python tools/classla_gate.py <checkpoints_dir> [--max N] [--files a.chk b.chk]"""
import glob
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NLP = None


def nlp():
    global _NLP
    if _NLP is None:
        import classla
        _NLP = classla.Pipeline("hr", processors="tokenize,pos", use_gpu=False,
                                dir=os.path.join(BASE, "data", "classla_resources"), logging_level="ERROR")
    return _NLP


def plain(path):
    raw = re.sub(r"<!--.*?-->", " ", open(path, encoding="utf-8", errors="ignore").read(), flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()


def analiza(tekst, max_znakova=6000):
    doc = nlp()(tekst[:max_znakova])
    ukupno = x = sumnjivih = 0
    primjeri = []
    for s in doc.sentences:
        w = [t for t in s.words if re.search(r"[A-Za-zČĆŽŠĐčćžšđ]", t.text)]
        if not w:
            continue
        nx = sum(1 for t in w if t.upos == "X")
        ukupno += len(w); x += nx
        if len(w) >= 4 and nx / len(w) >= 0.3:
            sumnjivih += 1
            if len(primjeri) < 3:
                primjeri.append(" ".join(t.text for t in s.words)[:90])
    return {"rijeci": ukupno, "x": x, "udio_x": round(x / max(ukupno, 1), 3), "sumnjive_rec": sumnjivih, "primjeri": primjeri}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    d = a[0]
    mx = int(a[a.index("--max") + 1]) if "--max" in a else 0
    fs = a[a.index("--files") + 1:] if "--files" in a else sorted(
        f for f in glob.glob(d + "/*.chk") if ".prevod" not in f and ".lektura" not in f)
    if mx:
        fs = fs[:mx]
    t0 = time.time()
    for f in fs:
        r = analiza(plain(f if os.path.isabs(f) else os.path.join(d, f)))
        if r["sumnjive_rec"]:
            print(os.path.basename(f), r["sumnjive_rec"], "sumnjivih rec |", r["primjeri"])
    print(f"gotovo: {len(fs)} blokova u {time.time()-t0:.0f}s")
