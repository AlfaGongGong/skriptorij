#!/usr/bin/env bash
# booklyfi_chk_naravno_fix.sh
# Vraća "naravno" (", ." i ",,"), popravlja part0221 i ćirilično 'о'.
#   bash booklyfi_chk_naravno_fix.sh                 -> dry-run (STARO/NOVO)
#   bash booklyfi_chk_naravno_fix.sh --apply         -> primjena + backup
#   ZAREZ_MODE=drop bash booklyfi_chk_naravno_fix.sh -> ",," se briše umjesto vraćanja riječi
set -u
REPO="/root/skriptorij"
CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
BK="/storage/emulated/0/booklyfi_checkpoints/_backup"
MODE="dry"; [ "${1:-}" = "--apply" ] && MODE="apply"
ZAREZ_MODE="${ZAREZ_MODE:-restore}"

# REPO GUARD (P18)
cd "$REPO" 2>/dev/null || { echo "STOP: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "STOP: nije repo"; exit 1; }
[ -d "$CK" ] || { echo "STOP: nema $CK"; exit 1; }

PY="venv/bin/python3"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs "$BK"
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/chk_naravno_fix_$TS.log"
clear

{
echo "=== chk_naravno_fix | mod=$MODE | zarez=$ZAREZ_MODE | $TS ==="

if [ "$MODE" = "apply" ]; then
    TAR="$BK/chk_pre_naravno_fix_$TS.tar.gz"
    tar -czf "$TAR" -C "$CK" . || { echo "Backup NEUSPJEO, prekid."; exit 1; }
    echo "Backup: $TAR"
fi

CK="$CK" MODE="$MODE" ZAREZ_MODE="$ZAREZ_MODE" "$PY" - << 'EOF_PY'
import os, re
from pathlib import Path

CK = Path(os.environ["CK"])
MODE = os.environ["MODE"]
ZM = os.environ["ZAREZ_MODE"]
RIJEC = "naravno"

SPEC = [("„, građanice Sutkinjo, .”", "„Naravno, građanice Sutkinjo.”")]
CYR_BAD, CYR_OK = "kompr\u043emisa", "kompromisa"
P_DOT = re.compile(r",[ \t]+\.")
P_DBL = re.compile(r",,")

cnt = {"spec": 0, "dot": 0, "dbl": 0, "cyr": 0}
changed = 0

def ctx(s, a, b, w=32):
    return s[max(0, a - w):b + w].replace("\n", "\\n")

for p in sorted(CK.glob("*.chk")):
    if p.name.endswith((".prevod.chk", ".lektura.chk")):
        continue
    orig = p.read_text("utf-8", "replace")
    t = orig
    ev = []

    for bad, good in SPEC:
        n = t.count(bad)
        if n:
            ev.append(("SPEC", bad, good))
            cnt["spec"] += n
            t = t.replace(bad, good)

    def r_dot(m):
        cnt["dot"] += 1
        new = ", " + RIJEC + "."
        ev.append(("DOT", ctx(m.string, m.start(), m.end()), new))
        return new
    t = P_DOT.sub(r_dot, t)

    def r_dbl(m):
        cnt["dbl"] += 1
        new = ", " + RIJEC + "," if ZM == "restore" else ""
        ev.append(("DBL", ctx(m.string, m.start(), m.end()), new if new else "(obrisano)"))
        return new
    t = P_DBL.sub(r_dbl, t)

    n = t.count(CYR_BAD)
    if n:
        cnt["cyr"] += n
        ev.append(("CYR", CYR_BAD, CYR_OK))
        t = t.replace(CYR_BAD, CYR_OK)

    if t != orig:
        changed += 1
        print(f"\n--- {p.name}")
        for k, a, b in ev:
            print(f"  [{k}] STARO: ...{a}...")
            print(f"        NOVO : {b}")
        if MODE == "apply":
            tmp = p.with_suffix(".chk.tmp")
            tmp.write_text(t, encoding="utf-8")
            os.replace(tmp, p)

print("\n=== Sažetak ===")
print(f"Fajlova za izmjenu : {changed}")
print(f"part0221 specijalno: {cnt['spec']}")
print(f"', .' zamjena      : {cnt['dot']}")
print(f"',,' zamjena       : {cnt['dbl']}")
print(f"ćirilično о        : {cnt['cyr']}")

# Provjera nakon (samo u apply modu)
if MODE == "apply":
    left = {"dot": 0, "dbl": 0, "cyr": 0}
    for p in CK.glob("*.chk"):
        if p.name.endswith((".prevod.chk", ".lektura.chk")):
            continue
        s = p.read_text("utf-8", "replace")
        left["dot"] += len(P_DOT.findall(s))
        left["dbl"] += len(P_DBL.findall(s))
        left["cyr"] += s.count(CYR_BAD)
    print(f"\nPreostalo nakon primjene: {left}")
    print("PRIMIJENJENO." if sum(left.values()) == 0 else "PAŽNJA: ima ostataka.")
else:
    print("\nDRY-RUN: ništa nije upisano. Primjena: bash booklyfi_chk_naravno_fix.sh --apply")
EOF_PY
echo "=== Log: $LOG ==="
} 2>&1 | tee "$LOG"
[ -x tools/out.sh ] && bash tools/out.sh "$LOG"
