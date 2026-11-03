#!/bin/bash
# T3.1b regresija: offline accuracy_derived nad sacuvanim blokovima + audit
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t31b_regresija_$TS.log"

{
echo "=== HEAD ==="
git log --oneline -1

echo
echo "=== Offline derived nad sacuvanim blokovima ==="
venv/bin/python3 << 'PYEOF'
import json

KF = {"leak": 5.0, "kraj_u_tagu": 3.0, "ratio_nizak": 3.0, "p_gubitak": 2.0}
KK = {"en_ostaci": 3.0, "imena_nedostaju": 2.0, "brojevi_razlika": 2.0}

def derived(v):
    d = 10.0
    for f in v.get("flags", []):
        d -= KF.get(f, 0.0)
    for c in v.get("kodovi", []):
        d -= KK.get(c, 0.0)
    return round(max(1.0, d), 1)

putanje = [
    "/storage/emulated/0/booklyfi_checkpoints/_skr_TWOC_test_3pogl/checkpoints/quality_accuracy.json",
    ".logs/t32_ck/quality_accuracy.json",
]
for p in putanje:
    d = json.load(open(p))
    cap = {k: derived(v) for k, v in d.items() if derived(v) < 10.0}
    print(f"\n{p}")
    print(f"  blokova: {len(d)}, sa capom (<10): {len(cap)}")
    for k, v in cap.items():
        print(f"    {k}: derived={v} flags={d[k].get('flags')} kodovi={d[k].get('kodovi')}")
    # blokovi bez flagova i bez kodova ne smiju biti capovani
    greske = [k for k, v in d.items() if not v.get("flags") and not v.get("kodovi") and derived(v) != 10.0]
    print(f"  GRESKA (cist blok capovan): {greske if greske else 'nema'}")
PYEOF

echo
echo "=== make audit-quick ==="
make audit-quick 2>&1 | tail -40

echo
echo "=== git status --short ==="
git status --short
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
