clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/overlap_redoslijed_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export U=/storage/emulated/0/Books/MoonReader/booklyfi/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO.epub
export S=/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub
export BOOK=/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub
export BAKS=/storage/emulated/0/Download/twoc_styled_prije_redoslijed_$TS.epub
[ -f "$U" ] || { echo "FAIL: nema $U"; exit 1; }
[ -f "$S" ] || { echo "FAIL: nema $S"; exit 1; }
[ -f "$BOOK" ] || { echo "FAIL: nema $BOOK"; exit 1; }
cp -p "$S" "$BAKS" || { echo "FAIL: backup nije uspio"; exit 1; }
{
echo "=== 0. Backup trenutnog STYLED-a ==="
ls -l "$BAKS"

echo
echo "=== 1. P1: commit prije izmjene ==="
git add -A && git commit -q -m "prije: fuzzy overlap prije egzaktnog"; git log --oneline -1

echo
echo "=== 2. STARO/NOVO epub/styler.py (tacno 1x) ==="
$PY - <<'PY'
import sys
p = "epub/styler.py"
s = open(p, encoding="utf-8").read()
staro = r'''                    _sk, _n = _skrati_overlap(_delovi_dedup[-1], _sl)
                    if _n > 0:
                        print(f"  [overlap] {_html_name}: skraceno {_n} rijeci")
                    if _n == 0:
                        _sk, _k, _wk = _skrati_overlap_fuzzy(_delovi_dedup[-1], _sl)
                        if _k > 0:
                            print(f"  [overlap~] {_html_name}: uklonjeno {_k} odlomaka ({_wk} rijeci)")
'''
novo = r'''                    # 2026-11-03: fuzzy (cuva <p> strukturu) prije egzaktnog (vraca goli tekst)
                    _sk, _k, _wk = _skrati_overlap_fuzzy(_delovi_dedup[-1], _sl)
                    _n = 0
                    if _k > 0:
                        print(f"  [overlap~] {_html_name}: uklonjeno {_k} odlomaka ({_wk} rijeci)")
                    else:
                        _sk, _n = _skrati_overlap(_delovi_dedup[-1], _sl)
                        if _n > 0:
                            print(f"  [overlap] {_html_name}: skraceno {_n} rijeci")
'''
n = s.count(staro)
print("STARO pojavljivanja =", n)
if n != 1:
    print("STOP: nista nije upisano"); sys.exit(1)
open(p, "w", encoding="utf-8").write(s.replace(staro, novo))
print("upisano")
PY
RC=$?
if [ $RC -eq 0 ]; then
  git diff epub/styler.py
  $PY -c "import ast; ast.parse(open('epub/styler.py').read()); print('ast OK')" \
   && $PY -m py_compile epub/styler.py && echo "py_compile OK" \
   && $PY -c "import epub.styler; print('import OK')"
  RC=$?
fi

if [ $RC -eq 0 ]; then
echo
echo "=== 3. Rebuild U + styler + mjerenje ==="
$PY - <<'PY'
import os, re, sys, zipfile, traceback, html, collections
from pathlib import Path
sys.path.insert(0, os.getcwd())
tag = re.compile(r"<[^>]+>")
par = re.compile(r"<p[\s>].*?</p>", re.S | re.I)

def mjeri(p):
    z = zipfile.ZipFile(p)
    n = dict(html=0, p=0, ascii=0, orocak=0, nepr=0, judge=0, grupa=0)
    maxw, grupe = {}, []
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
            if t.startswith(("\u2014", "\u2013")) and "\u201d" in t and "\u201e" not in t:
                n["orocak"] += 1
            n["nepr"] += t.count("NEPREVEDENO")
            n["judge"] += len(re.findall(r"\bJudge", t))
            mw = max(mw, len(t.split()))
            for sent in re.split(r"(?<=[.!?\u2026\u201d\"])\s+", t):
                kk = re.sub(r"\W+", " ", sent).strip().lower()
                if len(kk) >= 50:
                    poz[kk].append(i)
        for k, v in poz.items():
            if len(v) > 1:
                n["grupa"] += 1
                grupe.append((nm.split("/")[-1], v, k))
        maxw[nm.split("/")[-1]] = mw
    return n, maxw, grupe

prije, mw0, _ = mjeri(os.environ["BAKS"])
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
poslije, mw1, gr1 = mjeri(s)
print()
print("PRIJE  :", prije)
print("POSLIJE:", poslije)
print("najdulji odlomak (rijeci) prije -> poslije:")
for ch in ("part0179.html", "part0198.html", "part0200.html", "part0209.html", "part0192.html", "part0207.html"):
    print(f"   {ch}: {mw0.get(ch)} -> {mw1.get(ch)}")
print("top 5 poslije:", sorted(mw1.items(), key=lambda x: -x[1])[:5])
print(f"-- preostale ponovljene recenice u STYLED ({len(gr1)} grupa) --")
for ch, v, k in gr1[:14]:
    print(f"   {ch} odlomci {v}: {k[:70]}")
losi = []
for ch in ("part0179.html", "part0198.html", "part0200.html", "part0209.html"):
    if (mw1.get(ch) or 0) >= 250: losi.append(f"{ch} najdulji {mw1.get(ch)} >= 250")
if not (prije["p"] < poslije["p"] <= 6300): losi.append(f"p {prije['p']} -> {poslije['p']} izvan (prije, 6300]")
if poslije["grupa"] > 14: losi.append(f"grupa {poslije['grupa']} > 14")
if poslije["ascii"] > 100: losi.append(f"ascii {poslije['ascii']} > 100")
if poslije["judge"] or poslije["nepr"]: losi.append("judge/nepr != 0")
if poslije["orocak"] > 5: losi.append(f"orocak {poslije['orocak']} > 5")
print("VERDIKT:", "LOSE: " + "; ".join(losi) if losi else "OK")
sys.stdout.flush()
os._exit(7 if losi else 0)
PY
RC=$?
echo "(python exit: $RC)"
fi

if [ $RC -ne 0 ]; then
  echo
  echo "!!! PALO — P6: vracam epub/styler.py i prethodni STYLED"
  git checkout -- epub/styler.py && echo "styler.py vracen"
  cp -p "$BAKS" "$S" && ls -l "$S"
else
  echo
  echo "=== 4. Commit ==="
  git add epub/styler.py
  git commit -q -m "fix: styler fuzzy overlap prije egzaktnog (cuva odlomke)"
  git log --oneline -2
fi
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
