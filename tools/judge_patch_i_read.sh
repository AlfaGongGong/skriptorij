clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/judge_patch_read_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
[ -f tools/judge_fix2.sh ] || { echo "FAIL: nema tools/judge_fix2.sh"; exit 1; }
cp -p tools/judge_fix2.sh "tools/judge_fix2.sh.bak_$TS"
{
echo "=== 1. Patch judge_fix2.sh (STARO/NOVO, tacno 1x) ==="
$PY - <<'PY'
import sys
p = "tools/judge_fix2.sh"
s = open(p, encoding="utf-8").read()
staro = '''    if o == "Judgea":   return "Sutkinje", "gen", False
'''
novo = '''    if o == "Judgea":
        L0 = seg[max(0, m.start() - 45):m.start()]
        if re.search(r"(?<!\\w)upozorio\\s+$", L0, re.I):
            return "Sutkinju", "acc", False
        return "Sutkinje", "gen", False
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
  bash -n tools/judge_fix2.sh && echo "bash -n OK"
  $PY - <<'PY2'
import re
s = open("tools/judge_fix2.sh", encoding="utf-8").read()
bl = re.findall(r"<<'PY'\n(.*?)\nPY\n", s, flags=re.S)
for b in bl:
    compile(b, "judge_fix2", "exec")
print("python blokova kompajlirano:", len(bl))
PY2
  grep -n "upozorio" tools/judge_fix2.sh
else
  cp -p "tools/judge_fix2.sh.bak_$TS" tools/judge_fix2.sh && echo "vraceno iz backupa"
fi

echo
echo "=== 2. STYLER (samo cita): _dijalog + DIJALOG_TIPOGRAFIJA + redoslijed poziva ==="
$PY - <<'PY'
import ast, re
src = open("epub/styler.py", encoding="utf-8").read()
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.FunctionDef) and n.name == "_dijalog":
        seg = ast.get_source_segment(src, n).splitlines()
        print(f"--- epub/styler.py:{n.lineno} _dijalog ({len(seg)} linija, prvih 100) ---")
        print("\n".join(seg[:100]))
d = open("core/kalkovi/dijalog.py", encoding="utf-8").read().splitlines()
for i, l in enumerate(d):
    if l.startswith("DIJALOG_TIPOGRAFIJA"):
        print(f"--- core/kalkovi/dijalog.py:{i+1} DIJALOG_TIPOGRAFIJA (60 linija) ---")
        print("\n".join(d[i:i+60]))
        break
else:
    print("DIJALOG_TIPOGRAFIJA nije na pocetku linije u dijalog.py; grep:")
    print("\n".join(l for l in d if "DIJALOG_TIPOGRAFIJA" in l))
PY
echo "--- epub/styler.py 1395-1412 (redoslijed koraka) ---"
sed -n '1395,1412p' epub/styler.py
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
