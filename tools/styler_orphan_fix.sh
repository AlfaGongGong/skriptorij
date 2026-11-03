clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/styler_orphan_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export U=/storage/emulated/0/Books/MoonReader/booklyfi/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO.epub
export S=/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub
export BAKS=/storage/emulated/0/Download/twoc_styled_prije_orphan_$TS.epub
[ -f "$U" ] || { echo "FAIL: nema $U"; exit 1; }
[ -f "$S" ] || { echo "FAIL: nema $S"; exit 1; }
cp -p "$S" "$BAKS" || { echo "FAIL: backup nije uspio"; exit 1; }
{
echo "=== 0. Backup trenutnog STYLED-a ==="
ls -l "$BAKS"

echo
echo "=== 1. P1: commit prije izmjene ==="
git add -A && git commit -q -m "prije: styler siroce zatvarac u odlomku s crticom"; git log --oneline -1

echo
echo "=== 2. STARO/NOVO epub/styler.py (tacno 1x) ==="
$PY - <<'PY'
import sys
p = "epub/styler.py"
s = open(p, encoding="utf-8").read()
staro = '''        _dijalog(soup)
        _ukloni_duplikate_p(soup)
'''
novo = '''        _dijalog(soup)
        # 2026-11-03: siroce \u201d u odlomku s crticom (isti normalizator kao u pipelineu)
        try:
            from core.text_utils import _navodnici_u_tekstu
            soup = BeautifulSoup(_navodnici_u_tekstu(str(soup)), "html.parser")
        except Exception:
            logger.exception("[C3_fallback] styler: navodnici")
        _ukloni_duplikate_p(soup)
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
echo "=== 3. Styler na U + mjerenje (prije: ascii=136, otv=3625, zat=3800, orocak=146) ==="
$PY - <<'PY'
import os, re, sys, zipfile, traceback, html
from pathlib import Path
sys.path.insert(0, os.getcwd())
tag = re.compile(r"<[^>]+>")
par = re.compile(r"<p[\s>].*?</p>", re.S | re.I)

def mjeri(p):
    z = zipfile.ZipFile(p)
    n = dict(html=0, p=0, ascii=0, otv=0, zat=0, orocak=0, nepr=0, judge=0, dvz=0)
    for nm in z.namelist():
        if not nm.lower().endswith((".xhtml", ".html")):
            continue
        n["html"] += 1
        raw = z.read(nm).decode("utf-8", "ignore")
        for x in par.findall(raw):
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
    return n

prije = mjeri(os.environ["BAKS"])
try:
    from epub.manager import EpubStylerManager
    r = EpubStylerManager(epub_path=Path(os.environ["U"]), log_callback=lambda m, a="info": None).stilizuj()
    print("stilizacija:", {k: r.get(k) for k in ("ok", "chapters", "dropcaps_added", "error")})
    s = Path(r.get("epub_path", ""))
except Exception:
    traceback.print_exc(); s = Path("")
if not s.exists():
    print("STYLED NIJE nastao"); sys.stdout.flush(); os._exit(6)
poslije = mjeri(s)
print("PRIJE  :", prije)
print("POSLIJE:", poslije)
losi = []
if poslije["p"] != prije["p"]: losi.append(f"broj <p> {prije['p']} -> {poslije['p']}")
if poslije["ascii"] > 250: losi.append(f"ascii {poslije['ascii']} > 250")
if poslije["orocak"] >= prije["orocak"]: losi.append(f"orocak nije pao ({prije['orocak']} -> {poslije['orocak']})")
if poslije["judge"] != 0: losi.append("judge != 0")
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
  git commit -q -m "fix: styler uklanja siroce zatvarace u odlomku s crticom"
  git log --oneline -2
fi
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
