#!/bin/bash
# TWOC finalna provjera: checkpointi + imena + accuracy + EPUB (samo citanje)
cd /root/skriptorij || exit 1
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "/root/skriptorij" ] || { echo "STOP"; exit 1; }
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_final_check_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export EPUB_DIR="/storage/emulated/0/Books/MoonReader/STYLED"
export SRC_EPUB="/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub"
export KANON="/storage/emulated/0/Books/MoonReader/kanon/The_Wisdom_of_Crowds.json"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
venv/bin/python3 << 'PYEOF'
import os, re, sys, json, glob, zipfile, urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

CK = os.environ["CK"]
EPUB_DIR = os.environ["EPUB_DIR"]
SRC = os.environ["SRC_EPUB"]
KANON = os.environ["KANON"]

R = []
def add(level, msg):
    R.append((level, msg))
    print(f"  {level:<4} {msg}")
def sec(t):
    print(f"\n=== {t} ===")
def strip_sha(t):
    return re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
def plain(t):
    return re.sub(r"<[^>]+>", " ", t)

LEAK = re.compile(r"\{\s*[„\"“”]?\s*korektura")
JSONW = re.compile(r'^\s*\{\s*"[a-z_]+"\s*:')
ATTR_Q = re.compile(r"<[^<>]*\w=\s*[„“”][^<>]*>")
CUT = re.compile(r"<[^<>]*$")
BAJAZ = re.compile(r"Bajaz\w*")

# ---------- 1. status ----------
sec("1. Status servera")
try:
    with urllib.request.urlopen("http://127.0.0.1:8080/api/status", timeout=5) as r:
        st = json.loads(r.read().decode())
    print(f"  status={st.get('status')} pct={st.get('pct')} ok={st.get('ok')}")
    s = str(st.get("status", "")).lower()
    if "run" in s or "proc" in s or "busy" in s:
        add("WARN", "obrada jos traje, rezultat nije konacan")
except Exception as e:
    add("INFO", f"server nedostupan ({type(e).__name__}) — provjera samo fajlova")

# ---------- 2. checkpointi ----------
sec("2. Checkpointi")
chk = {}
mt_max = 0
for p in glob.glob(CK + "/*.chk"):
    n = os.path.basename(p)
    if n.endswith((".prevod.chk", ".lektura.chk")):
        continue
    try:
        chk[n[:-4]] = strip_sha(open(p, encoding="utf-8", errors="replace").read())
        mt_max = max(mt_max, os.path.getmtime(p))
    except Exception:
        pass
print(f"  finalnih: {len(chk)} | .prevod.chk: {len(glob.glob(CK + '/*.prevod.chk'))}")
if not chk:
    add("FAIL", "nema checkpointa — provjeri putanju CK")
    sys.exit(1)

def brojac(naziv, pred, nivo="FAIL", limit=8):
    lista = sorted(k for k, t in chk.items() if pred(t))
    if lista:
        add(nivo, f"{naziv}: {len(lista)}  npr. {lista[:limit]}")
    else:
        add("OK", f"{naziv}: 0")
    return lista

brojac("prazni/prekratki blokovi (<20 znakova)", lambda t: len(t.strip()) < 20)
brojac("marker NEPREVEDENO", lambda t: "NEPREVEDENO" in t)
brojac("odsjecen HTML (kraj u tagu)", lambda t: bool(CUT.search(t.rstrip())))
brojac("leak {„korektura", lambda t: bool(LEAK.search(t)))
brojac("rijec 'korektura' u tekstu (moze biti legitimno)", lambda t: "korektura" in t.lower(), "WARN")
brojac("JSON omotac na pocetku bloka", lambda t: bool(JSONW.match(t)))
brojac("„ “ ” u HTML atributima", lambda t: bool(ATTR_Q.search(t)))
brojac("ASCII \" u tekstu (tipografija)", lambda t: '"' in plain(t), "WARN")
baj = brojac("Bajaz (pogresno ime)", lambda t: bool(BAJAZ.search(t)))
n_bay = sum(len(re.findall(r"Bayaz\w*", t)) for t in chk.values())
print(f"  Bayaz pojava: {n_bay} | Bajaz pojava: {sum(len(BAJAZ.findall(t)) for t in chk.values())}")

# ---------- 3. kanon: imena ----------
sec("3. Kanon vs izlaz")
try:
    termini = json.load(open(KANON, encoding="utf-8"))["termini"]
    hr_all = " ".join(plain(t) for t in chk.values())
    src_parts = {}
    with zipfile.ZipFile(SRC) as z:
        for n in z.namelist():
            if n.lower().endswith((".xhtml", ".html", ".htm")):
                src_parts[os.path.basename(n)] = plain(z.read(n).decode("utf-8", "replace"))
    pokriveni = {k.rsplit("_blok_", 1)[0] for k in chk}
    src_txt = " ".join(t for n, t in src_parts.items() if n in pokriveni)
    print(f"  izvornih dijelova: {len(src_parts)} | pokrivenih checkpointom: {len(pokriveni & set(src_parts))}")

    top = sorted(((k, v) for k, v in termini.items()
                  if v.get("hr") == k and len(k) >= 4 and v.get("potvrdjeno")),
                 key=lambda kv: -kv[1].get("broj_pojava", 0))[:25]
    loseg = []
    for ime, _ in top:
        rx = re.compile(r"(?<!\w)" + re.escape(ime) + r"\w*")
        e, h = len(rx.findall(src_txt)), len(rx.findall(hr_all))
        if e >= 15 and (h == 0 or h / e < 0.8):
            loseg.append((ime, e, h))
    if loseg:
        add("WARN", f"imena koja nestaju/mijenjaju se (ime, EN, HR): {loseg[:8]}")
    else:
        add("OK", "top-25 imena (hr==en): HR/EN omjer >= 0.8")

    zaost = []
    for en, v in termini.items():
        hr = v.get("hr")
        if hr and hr != en and len(en) >= 4 and v.get("potvrdjeno"):
            c = len(re.findall(r"(?<!\w)" + re.escape(en) + r"(?!\w)", hr_all))
            if c:
                zaost.append((en, c))
    zaost.sort(key=lambda x: -x[1])
    if zaost:
        add("WARN", f"EN oblik ostao umjesto kanonskog prijevoda: {zaost[:10]}")
    else:
        add("OK", "nema zaostalih EN oblika prevedenih termina")
except Exception as e:
    add("WARN", f"kanon/izvornik provjera preskocena: {type(e).__name__}: {e}")
    src_parts = {}

# ---------- 4. ocjene ----------
sec("4. Ocjene")
sc = {}
try:
    raw = json.load(open(CK + "/quality_scores.json", encoding="utf-8"))
    for k, v in raw.items():
        if isinstance(v, dict):
            v = v.get("score")
        try:
            sc[k] = float(v)
        except Exception:
            pass
except Exception as e:
    add("FAIL", f"quality_scores.json: {type(e).__name__}")
if sc:
    b = Counter()
    for v in sc.values():
        b["<=1.0" if v <= 1.0 else "<6" if v < 6 else "6-8" if v < 8 else "8-9" if v < 9 else ">=9"] += 1
    print(f"  ukupno: {len(sc)} | prosjek: {sum(sc.values())/len(sc):.2f} | " +
          " ".join(f"{k}={b[k]}" for k in ("<=1.0", "<6", "6-8", "8-9", ">=9")))
    bez = sorted(set(chk) - set(sc))
    sirote = sorted(set(sc) - set(chk))
    add("OK" if not bez else "WARN", f"blokova bez ocjene: {len(bez)} {bez[:5]}")
    add("OK" if not sirote else "INFO", f"ocjena bez bloka: {len(sirote)}")
    nisko = sum(1 for k in chk if sc.get(k, 10) < 6)
    udio = nisko / len(chk)
    add("OK" if udio <= 0.05 else "WARN" if udio <= 0.15 else "FAIL",
        f"blokovi sa ocjenom < 6.0: {nisko}/{len(chk)} ({udio:.1%})")
try:
    hrv = json.load(open(CK + "/human_review.json", encoding="utf-8"))
    print(f"  human_review stavki: {len(hrv)}")
except Exception:
    pass

# ---------- 5. accuracy (T3.1b) ----------
sec("5. Accuracy")
try:
    qa = json.load(open(CK + "/quality_accuracy.json", encoding="utf-8"))
    fl, kod = Counter(), Counter()
    for v in qa.values():
        fl.update(v.get("flags", []))
        kod.update(v.get("kodovi", []))
    print(f"  blokova u accuracy: {len(qa)} | flagovi: {dict(fl) or 'cisto'} | kodovi: {dict(kod) or 'cisto'}")
    pokr = len(set(qa) & set(chk))
    add("OK" if pokr >= 0.9 * len(chk) else "INFO", f"accuracy pokriva {pokr}/{len(chk)} blokova")
    der = {k: v["accuracy_derived"] for k, v in qa.items() if v.get("accuracy_derived") is not None}
    add("OK" if der or not qa else "WARN", f"accuracy_derived popunjen: {len(der)}/{len(qa)}")
    ispod = sorted(k for k, d in der.items() if d < 10)
    print(f"  blokova sa accuracy_derived < 10: {len(ispod)}")
    krsi = sorted(k for k, d in der.items() if k in sc and sc[k] > d + 1e-9)
    add("OK" if not krsi else "WARN",
        f"ocjena > accuracy_derived (cap nije primijenjen — stari blok?): {len(krsi)} {krsi[:5]}")
except Exception as e:
    add("INFO", f"quality_accuracy.json nedostupan: {type(e).__name__}")

# ---------- 6. EPUB ----------
sec("6. Finalni EPUB")
epubs = sorted(glob.glob(EPUB_DIR + "/*Wisdom*PREVEDENO_STYLED.epub"), key=os.path.getmtime)
if not epubs:
    add("FAIL", "nema finalnog EPUB-a u " + EPUB_DIR)
else:
    ep = epubs[-1]
    print(f"  {os.path.basename(ep)} | {os.path.getsize(ep)//1024} KB")
    if os.path.getmtime(ep) < mt_max:
        add("WARN", "EPUB je stariji od zadnjeg checkpointa — treba ponovo spakovati")
    else:
        add("OK", "EPUB je noviji od svih checkpointa")
    try:
        with zipfile.ZipFile(ep) as z:
            bad = z.testzip()
            add("OK" if not bad else "FAIL", f"zip integritet{'' if not bad else ': ' + bad}")
            nl = z.infolist()
            mt_ok = nl[0].filename == "mimetype" and nl[0].compress_type == zipfile.ZIP_STORED
            add("OK" if mt_ok else "FAIL", "mimetype prvi i nekompresovan")
            htmls = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
            xml_err, nepr, leak, baj_e, attr = [], 0, 0, 0, 0
            for n in htmls:
                raw = z.read(n)
                try:
                    ET.fromstring(raw)
                except Exception as e:
                    xml_err.append(f"{os.path.basename(n)}: {str(e)[:40]}")
                t = raw.decode("utf-8", "replace")
                nepr += "NEPREVEDENO" in t
                leak += bool(LEAK.search(t))
                baj_e += len(BAJAZ.findall(t))
                attr += bool(ATTR_Q.search(t))
            add("OK" if not xml_err else "FAIL", f"XHTML ispravnost: {len(xml_err)} gresaka u {len(htmls)} dijelova {xml_err[:3]}")
            add("OK" if not nepr else "FAIL", f"NEPREVEDENO u EPUB-u: {nepr} dijelova")
            add("OK" if not leak else "FAIL", f"leak u EPUB-u: {leak} dijelova")
            add("OK" if not baj_e else "FAIL", f"Bajaz u EPUB-u: {baj_e}")
            add("OK" if not attr else "FAIL", f"„ u atributima u EPUB-u: {attr} dijelova")
            if src_parts:
                add("OK" if len(htmls) >= len(src_parts) else "WARN",
                    f"dijelova: EPUB {len(htmls)} vs izvornik {len(src_parts)}")
    except Exception as e:
        add("FAIL", f"EPUB se ne moze otvoriti: {type(e).__name__}: {e}")

# ---------- 7. pokrivenost izvornika ----------
if src_parts:
    sec("7. Dijelovi izvornika bez checkpointa")
    prazno = sorted(n for n, t in src_parts.items()
                    if len(t.split()) >= 150 and n not in {k.rsplit('_blok_', 1)[0] for k in chk})
    add("OK" if not prazno else "WARN",
        f"dijelova s >=150 rijeci bez checkpointa: {len(prazno)} {prazno[:8]}")

# ---------- presuda ----------
sec("PRESUDA")
nf = sum(1 for l, _ in R if l == "FAIL")
nw = sum(1 for l, _ in R if l == "WARN")
print(f"  FAIL={nf} WARN={nw} OK={sum(1 for l, _ in R if l == 'OK')}")
if nf == 0 and nw == 0:
    print("  ✅ KNJIGA SPREMNA ZA CITANJE")
elif nf == 0:
    print("  🟡 CITLJIVO, ali pregledaj WARN stavke gore")
else:
    print("  ❌ NIJE SPREMNO — FAIL stavke:")
    for l, m in R:
        if l == "FAIL":
            print("   -", m[:200])
print(f"  EPUB: {EPUB_DIR}")
sys.exit(1 if nf else 0)
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
echo "Log: $LOG"
