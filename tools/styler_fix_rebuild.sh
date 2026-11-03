clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/styler_fix_rebuild_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export U=/storage/emulated/0/Books/MoonReader/booklyfi/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO.epub
export S=/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub
export BOOK=/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub
BAK=/storage/emulated/0/Download/twoc_pre_final_$TS
mkdir -p "$BAK"
[ -f "$S" ] && cp -p "$S" "$BAK/"
[ -f "$U" ] && cp -p "$U" "$BAK/"
[ -f "$BOOK" ] || { echo "FAIL: nema $BOOK"; exit 1; }
{
echo "=== 0. Backup: $BAK ==="
ls -l "$BAK"

echo
echo "=== 1. P1: commit prije izmjene ==="
git add -A && git commit -q -m "prije: styler _dijalog ne vraca tipografske navodnike u ASCII" ; git log --oneline -1

echo
echo "=== 2. STARO/NOVO epub/styler.py (tacno 1x) ==="
$PY - <<'PY'
import sys
p = "epub/styler.py"
s = open(p, encoding="utf-8").read()
staro = '''        for pattern, repl in DIJALOG_TIPOGRAFIJA:
            new = re.sub(pattern, repl, new)
'''
novo = '''        for pattern, repl in DIJALOG_TIPOGRAFIJA:
            # 2026-11-03: preskoci pravila koja \u201e\u2026\u201d vracaju u ASCII "
            if '"' in repl:
                continue
            new = re.sub(pattern, repl, new)
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
if [ $RC -ne 0 ]; then
  echo "!!! PALO — P6: vracam epub/styler.py"
  git checkout -- epub/styler.py
  echo "STOP"; exit 1
fi

echo
echo "=== 3. Judge apply (backup .chk ide unutra; staje ako ne uspije) ==="
bash tools/judge_fix2.sh apply > /dev/null 2>&1
RC=$?
L=$(ls -t .logs/judge2_apply_*.log 2>/dev/null | head -1)
echo "(judge exit: $RC, log: $L)"
[ $RC -eq 0 ] || { echo "STOP: judge apply nije prosao, rebuild se ne pokrece"; exit 1; }
sed -n '1,12p' "$L"
grep -n "part0221 acc\|POSLIJE" "$L"

echo
echo "=== 4. Rebuild U (finalize) + styler + mjerenje ==="
$PY - <<'PY'
import os, re, sys, time, zipfile, traceback, html
from pathlib import Path
sys.path.insert(0, os.getcwd())
tag = re.compile(r"<[^>]+>")
par = re.compile(r"<p[\s>].*?</p>", re.S | re.I)

def log(m, t="info"):
    pass

def mjeri(p):
    z = zipfile.ZipFile(p)
    n = dict(html=0, ascii=0, otv=0, zat=0, orocak=0, nepr=0, judge=0, dvz=0)
    for nm in z.namelist():
        if not nm.lower().endswith((".xhtml", ".html")):
            continue
        n["html"] += 1
        raw = z.read(nm).decode("utf-8", "ignore")
        for x in par.findall(raw):
            t = html.unescape(tag.sub("", x)).strip()
            n["ascii"] += t.count('"')
            n["otv"] += t.count("\u201e")
            n["zat"] += t.count("\u201d")
            if t.startswith(("\u2014", "\u2013")) and "\u201d" in t and "\u201e" not in t:
                n["orocak"] += 1
            n["nepr"] += t.count("NEPREVEDENO")
            n["judge"] += len(re.findall(r"\bJudge", t))
            n["dvz"] += t.count(",,")
    print(f"  {Path(p).name}:\n    {n}")

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
t0 = time.time()
try:
    e.generate_ncx()
    e.finalize()
except Exception:
    traceback.print_exc(); sys.stdout.flush(); os._exit(4)
u = Path(ss.get("output_file", ""))
print("U:", u, "| postoji:", u.exists())
if not u.exists():
    sys.stdout.flush(); os._exit(5)
try:
    from epub.manager import EpubStylerManager
    r = EpubStylerManager(epub_path=u, log_callback=log).stilizuj()
    print("stilizacija:", {k: r.get(k) for k in ("ok", "chapters", "dropcaps_added", "error")})
    s = Path(r.get("epub_path", ""))
except Exception:
    traceback.print_exc(); s = Path("")
print()
print("=== Mjerenje (prije: U ascii=1274, S ascii=6622, judge=150/148) ===")
mjeri(u)
if s.exists():
    mjeri(s)
else:
    print("STYLED NIJE nastao")
sys.stdout.flush()
os._exit(0 if s.exists() else 6)
PY
echo "(python exit: $?)"
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
