#!/bin/bash
# TWOC: ponovno primijeni popravak navodnika na .chk (idempotentno, sa backupom)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_navodnici_ponovo_$TS.log"
BK=".logs/twoc_nav_bak_$TS"
mkdir -p "$BK"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export BK

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
git status --short --untracked-files=no | grep text_utils
grep -c "_navodnici_u_tekstu" core/text_utils.py | sed 's/^/_navodnici_u_tekstu u kodu: /'
curl -s -m 5 http://127.0.0.1:8080/api/status | head -c 200; echo

venv/bin/python3 << 'PYEOF'
import os, re, sys, glob, shutil
sys.path.insert(0, ".")
from core.text_utils import _navodnici_u_tekstu as nav
CK, BK = os.environ["CK"], os.environ["BK"]
tag = re.compile(r"<[^>]+>")
qch = "\"\u201c\u201d\u201e"
izm = skip = 0
for p in sorted(glob.glob(CK + "/*.chk")):
    if p.endswith((".prevod.chk", ".lektura.chk")): continue
    t = open(p, encoding="utf-8", errors="replace").read()
    if "NEPREVEDENO" in t: continue
    n = nav(t)
    if n == t: continue
    if tag.findall(t) != tag.findall(n) or \
       re.sub("[" + qch + "]", "", tag.sub("", t)) != re.sub("[" + qch + "]", "", tag.sub("", n)):
        skip += 1; print("PRESKOCEN:", os.path.basename(p)); continue
    shutil.copy2(p, BK)
    open(p + ".tmp", "w", encoding="utf-8").write(n)
    os.replace(p + ".tmp", p)
    izm += 1
print(f"izmijenjeno: {izm} | preskoceno: {skip} | backup: {BK}")
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
