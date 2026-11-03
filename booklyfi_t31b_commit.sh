#!/bin/bash
# T3.1b commit: samo core/metrics.py i processing/pipeline.py
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t31b_commit_$TS.log"

{
echo "=== HEAD prije ==="
git log --oneline -1

echo
echo "=== Sintaksa ==="
venv/bin/python3 -m py_compile core/metrics.py processing/pipeline.py \
  && echo "py_compile OK" || { echo "SINTAKSA PALA -> STOP"; exit 1; }

echo
echo "=== Staged samo 2 fajla ==="
git add core/metrics.py processing/pipeline.py
git diff --cached --stat
BROJ=$(git diff --cached --name-only | wc -l)
if [ "$BROJ" -ne 2 ]; then
    echo "STOP: u stage-u je $BROJ fajlova, ocekivano 2"
    git reset -q
    exit 1
fi

git commit -q -F - << 'MSG'
T3.1b: konacna ocjena = min(LLM, accuracy_derived)

- metrics.accuracy_shadow: accuracy_derived = 10 - kazne
  (flagovi: leak -5, kraj_u_tagu -3, ratio_nizak -3, p_gubitak -2;
   kodovi: en_ostaci -3, imena_nedostaju -2, brojevi_razlika -2;
   donji prag 1.0). Flag "brojevi" se ne racuna (isti signal kao kod).
- pipeline._quality_scoring: _cap_acc() na sva 3 mjesta upisa
  (paratekst 8.5, nonprose 10.0, glavna grana poslije ratio cap-ova);
  _acc = {} prije try, pa bez capa ako shadow padne.
- Blokovi bez flagova/kodova: ocjena nepromijenjena.

Zasto: LLM scorer ne vidi EN, ocjenjuje stil. check_accuracy vidi EN,
mjeri tacnost. Kad se ne slazu, vjerujemo determinističkom. Nonprose
grana je propustala leak u TOC-u s 10.0.

Test: unit T1 4/4; _quality_scoring sa lazim self (leak 8.5->5.0, cist
8.5); offline TWOC_test_3pogl 12/12 bez capa; t32_ck leak blok 1.0;
make audit-quick FAIL=0.
MSG

echo
echo "=== HEAD poslije ==="
git log --oneline -1
echo
echo "=== git status --short ==="
git status --short
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
