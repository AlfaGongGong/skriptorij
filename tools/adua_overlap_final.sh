clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/adua_overlap_final_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export U=/storage/emulated/0/Books/MoonReader/booklyfi/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO.epub
export S=/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub
export BOOK=/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub
export CHK=/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints
export BAKS=/storage/emulated/0/Download/twoc_styled_prije_overlap_$TS.epub
[ -f "$U" ] || { echo "FAIL: nema $U"; exit 1; }
[ -f "$S" ] || { echo "FAIL: nema $S"; exit 1; }
[ -f "$BOOK" ] || { echo "FAIL: nema $BOOK"; exit 1; }
[ -f tools/adua_dup2.sh ] || { echo "FAIL: nema tools/adua_dup2.sh"; exit 1; }
cp -p "$S" "$BAKS" || { echo "FAIL: backup nije uspio"; exit 1; }
{
echo "=== 0. Backup trenutnog STYLED-a ==="
ls -l "$BAKS"

echo
echo "=== 1. P1: commit prije izmjene ==="
git add -A && git commit -q -m "prije: adua padezi + fuzzy overlap u styleru"; git log --oneline -1

echo
echo "=== 2. Adua apply (backup .chk ide unutra) ==="
bash tools/adua_dup2.sh apply > /dev/null 2>&1
RC=$?
L=$(ls -t .logs/adua_dup2_apply_*.log 2>/dev/null | head -1)
echo "(adua exit: $RC, log: $L)"
if [ $RC -ne 0 ]; then echo "STOP: adua apply nije prosao"; exit 1; fi
grep -n "MIJENJA SE\|POSLIJE" "$L"
if ! grep -q "MIJENJA SE: 25" "$L" || ! grep -q "preostalo golo 'Adua' u .chk = 7" "$L"; then
  echo "!!! brojevi ne odgovaraju — vracam .chk iz backupa"
  T=$(ls -t /storage/emulated/0/Download/twoc_chk_bak_adua2_*.tar.gz | head -1)
  tar xzf "$T" -C "$(dirname "$CHK")" && echo "vraceno iz $T"
  exit 1
fi

echo
echo "=== 3. STARO/NOVO epub/styler.py (svako tacno 1x) + testovi ==="
$PY - <<'PY'
import sys
p = "epub/styler.py"
s = open(p, encoding="utf-8").read()

staro1 = r'''def _spoji_blokove(delovi):
'''
novo1 = r'''def _skrati_overlap_fuzzy(prethodni, sljedeci, prag=0.85, min_znakova=60, zadnjih=60):
    """2026-11-03: fuzzy overlap na razini odlomaka. Ako pocetak sljedeceg bloka
    priblizno (>=prag) ponavlja zadnje odlomke prethodnog, ukloni ih iz sljedeceg.
    Vraca (novi_sljedeci, broj_odlomaka, broj_rijeci); bez promjene (sljedeci, 0, 0)."""
    import difflib as _dl
    import html as _hh
    import re as _re

    def _norm(t):
        t = _re.sub(r"<[^>]+>", " ", t)
        return _re.sub(r"\W+", " ", _hh.unescape(t).lower()).strip()

    def _slican(a, b):
        if not a or not b:
            return False
        if a == b:
            return True
        sm = _dl.SequenceMatcher(None, a, b, autojunk=False)
        return (
            sm.real_quick_ratio() >= prag
            and sm.quick_ratio() >= prag
            and sm.ratio() >= prag
        )

    def _dijeli(t):
        tx, poz = [], []
        if "<p" in t.lower():
            for m in _re.finditer(r"<p[\s>].*?</p>", t, flags=_re.S | _re.I):
                n = _norm(m.group(0))
                if n:
                    tx.append(n)
                    poz.append(m.end())
            return tx, (lambda k: t[poz[k - 1]:])
        dijelovi = _re.split(r"\n\s*\n", t)
        for i, x in enumerate(dijelovi):
            n = _norm(x)
            if n:
                tx.append(n)
                poz.append(i)
        return tx, (lambda k: "\n\n".join(dijelovi[poz[k - 1] + 1:]))

    pt, _ = _dijeli(prethodni)
    nt, rez = _dijeli(sljedeci)
    if not pt or not nt:
        return sljedeci, 0, 0
    for j in range(max(0, len(pt) - zadnjih), len(pt)):
        if not _slican(pt[j], nt[0]):
            continue
        k = 0
        while j + k < len(pt) and k < len(nt) and _slican(pt[j + k], nt[k]):
            k += 1
        if j + k == len(pt) and sum(len(x) for x in nt[:k]) >= min_znakova:
            return rez(k), k, sum(len(x.split()) for x in nt[:k])
    return sljedeci, 0, 0


def _spoji_blokove(delovi):
'''
staro2 = r'''                    _sk, _n = _skrati_overlap(_delovi_dedup[-1], _sl)
                    if _n > 0:
                        print(f"  [overlap] {_html_name}: skraceno {_n} rijeci")
'''
novo2 = staro2 + r'''                    if _n == 0:
                        _sk, _k, _wk = _skrati_overlap_fuzzy(_delovi_dedup[-1], _sl)
                        if _k > 0:
                            print(f"  [overlap~] {_html_name}: uklonjeno {_k} odlomaka ({_wk} rijeci)")
'''
for i, a in enumerate((staro1, staro2), 1):
    n = s.count(a)
    print(f"STARO {i}: pojavljivanja = {n}")
    if n != 1:
        print("STOP: nista nije upisano"); sys.exit(1)
s = s.replace(staro1, novo1).replace(staro2, novo2)
open(p, "w", encoding="utf-8").write(s)
print("upisano")
PY
RC=$?
if [ $RC -eq 0 ]; then
  git diff --stat epub/styler.py
  $PY -c "import ast; ast.parse(open('epub/styler.py').read()); print('ast OK')" \
   && $PY -m py_compile epub/styler.py && echo "py_compile OK" \
   && $PY -c "import epub.styler; print('import OK')"
  RC=$?
fi
if [ $RC -eq 0 ]; then
$PY - <<'PY'
from epub.styler import _skrati_overlap_fuzzy as f
pv = "<p>Prvi odlomak je posve drugačiji.</p><p>— To zvuči više kao izlika nego kao razlog, promrmlja Jurand.</p><p>Leo ga poprijeko pogleda, namršten.</p>"
nx = "<p>— To zvuči više kao izlika nego kao razlog — promrmlja Jurand.</p><p>Leo ga poprijeko pogleda, namršten.</p><p>Potpuno novi odlomak koji nema veze s prethodnim.</p>"
r, k, w = f(pv, nx)
ok1 = (k == 2 and "Potpuno novi" in r and "Jurand" not in r)
r2, k2, w2 = f(pv, "<p>Nešto sasvim treće i novo.</p><p>I još jedan odlomak.</p>")
ok2 = (k2 == 0 and r2.startswith("<p>Nešto"))
pvp = "Prvi odlomak.\n\n— To zvuči više kao izlika nego kao razlog, promrmlja Jurand.\n\nLeo ga poprijeko pogleda, namršten."
nxp = "— To zvuči više kao izlika nego kao razlog — promrmlja Jurand.\n\nLeo ga poprijeko pogleda, namršten.\n\nPotpuno novi odlomak."
r3, k3, w3 = f(pvp, nxp)
ok3 = (k3 == 2 and r3.strip() == "Potpuno novi odlomak.")
print("test HTML preklapanje :", "OK" if ok1 else f"FAIL k={k} r={r!r}")
print("test bez preklapanja  :", "OK" if ok2 else f"FAIL k={k2}")
print("test obican tekst     :", "OK" if ok3 else f"FAIL k={k3} r={r3!r}")
raise SystemExit(0 if (ok1 and ok2 and ok3) else 1)
PY
RC=$?
fi

if [ $RC -eq 0 ]; then
echo
echo "=== 4. Rebuild U + styler + mjerenje ==="
$PY - <<'PY'
import os, re, sys, zipfile, traceback, html, collections
from pathlib import Path
sys.path.insert(0, os.getcwd())
tag = re.compile(r"<[^>]+>")
par = re.compile(r"<p[\s>].*?</p>", re.S | re.I)

def mjeri(p):
    z = zipfile.ZipFile(p)
    n = dict(html=0, p=0, ascii=0, otv=0, zat=0, orocak=0, nepr=0, judge=0, dvz=0,
             grupa=0, veliki=0, adua=0, adue=0, adui=0, aduu=0)
    maxw = {}
    for nm in z.namelist():
        if not nm.lower().endswith((".xhtml", ".html")):
            continue
        n["html"] += 1
        raw = z.read(nm).decode("utf-8", "ignore")
        poz = collections.defaultdict(list)
        mw = 0
        for i, x in enumerate(par.findall(raw)):
            n["p"] += 1
            t = html.unescape(tag.sub("", x)).strip()
            n["ascii"] += t.count('"')
            n["otv"] += t.count("\u201e")
            n["zat"] += t.count("\u201d")
            if t.startswith(("\u2014", "\u2013")) and "\u201d" in t and "\u201e" not in t:
                n["orocak"] += 1
            n["nepr"] += t.count("NEPREVEDENO")
            n["judge"] += len(re.findall(r"\bJudge", t))
            n["dvz"] += t.count(",,")
            for k in ("adua", "adue", "adui", "aduu"):
                n[k] += len(re.findall(r"\b" + k.capitalize() + r"\b", t))
            w = len(t.split())
            mw = max(mw, w)
            if w >= 200:
                n["veliki"] += 1
            for sent in re.split(r"(?<=[.!?\u2026\u201d\"])\s+", t):
                kk = re.sub(r"\W+", " ", sent).strip().lower()
                if len(kk) >= 50:
                    poz[kk].append(i)
        n["grupa"] += sum(1 for v in poz.values() if len(v) > 1)
        maxw[nm.split("/")[-1]] = mw
    return n, maxw

prije, mw0 = mjeri(os.environ["BAKS"])
try:
    from core.engine import SkriptorijAllInOne
except Exception:
    traceback.print_exc(); sys.exit(2)
ss, sc = {}, {}
e = SkriptorijAllInOne(os.environ["BOOK"], "V10_TURBO", ss, sc)
if "_skr_The_Wisdom_of_Crowds" not in str(e.work_dir):
    print("STOP: work_dir nije TWOC:", e.work_dir)
    sys.stdout.flush(); os._exit(3)
if not getattr(e, "html_files", None):
    e.html_files = sorted((Path(e.work_dir) / "text").glob("*.html"))
try:
    e.generate_ncx()
    e.finalize()
except Exception:
    traceback.print_exc(); sys.stdout.flush(); os._exit(4)
u = Path(ss.get("output_file", ""))
if not u.exists():
    print("U nije nastao"); sys.stdout.flush(); os._exit(5)
try:
    from epub.manager import EpubStylerManager
    r = EpubStylerManager(epub_path=u, log_callback=lambda m, a="info": None).stilizuj()
    print("stilizacija:", {k: r.get(k) for k in ("ok", "chapters", "dropcaps_added", "error")})
    s = Path(r.get("epub_path", ""))
except Exception:
    traceback.print_exc(); s = Path("")
if not s.exists():
    print("STYLED NIJE nastao"); sys.stdout.flush(); os._exit(6)
poslije, mw1 = mjeri(s)
print()
print("PRIJE  :", prije)
print("POSLIJE:", poslije)
dp = prije["p"] - poslije["p"]
print(f"odlomaka uklonjeno: {dp} (simulacija na .chk: do 134)")
print("najdulji odlomak (rijeci) prije -> poslije:")
for ch in ("part0179.html", "part0192.html", "part0198.html", "part0200.html", "part0207.html", "part0209.html"):
    print(f"   {ch}: {mw0.get(ch)} -> {mw1.get(ch)}")
top = sorted(mw1.items(), key=lambda x: -x[1])[:5]
print("top 5 najduljih odlomaka poslije:", top)
losi = []
if not (20 <= dp <= 160): losi.append(f"uklonjeno odlomaka {dp} izvan [20,160]")
if poslije["ascii"] > 100: losi.append(f"ascii {poslije['ascii']} > 100")
if poslije["judge"] or poslije["nepr"]: losi.append("judge/nepr != 0")
if poslije["orocak"] > 5: losi.append(f"orocak {poslije['orocak']} > 5")
if poslije["grupa"] >= prije["grupa"]: losi.append(f"grupa duplikata nije pala ({prije['grupa']} -> {poslije['grupa']})")
print("VERDIKT:", "LOSE: " + "; ".join(losi) if losi else "OK")
sys.stdout.flush()
os._exit(7 if losi else 0)
PY
RC=$?
echo "(python exit: $RC)"
fi

if [ $RC -ne 0 ]; then
  echo
  echo "!!! PALO — P6: vracam epub/styler.py i prethodni STYLED (Adua u .chk ostaje; backup .chk je u Download)"
  git checkout -- epub/styler.py && echo "styler.py vracen"
  cp -p "$BAKS" "$S" && ls -l "$S"
else
  echo
  echo "=== 5. Commit ==="
  git add epub/styler.py
  git commit -q -m "fix: styler fuzzy overlap blokova (_skrati_overlap_fuzzy)"
  git log --oneline -2
fi
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
