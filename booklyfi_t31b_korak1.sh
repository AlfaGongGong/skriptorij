#!/bin/bash
# T3.1b Korak 1: accuracy_derived u core/metrics.py (accuracy_shadow)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t31b_korak1_$TS.log"
BAK=".logs/metrics_backup_$TS.py"

{
echo "=== HEAD ==="
git log --oneline -1

cp core/metrics.py "$BAK" || { echo "BACKUP NEUSPJEO"; exit 1; }
echo "Backup: $BAK"

echo
echo "=== PRIMJENA ==="
venv/bin/python3 << 'PYEOF'
import sys

PUTANJA = "core/metrics.py"

STARO = '''    out["flags"] = flags
    return out
'''

NOVO = '''    # 2026-11-01 T3.1b: deterministicka ocjena. LLM scorer ne vidi EN, ovo
    # vidi. Kad se ne slazu, vjerujemo determinističkom (min u pipeline.py).
    # Kazne iz flagova (rade i bez EN) + kodova (samo uz EN). "brojevi" flag
    # se NE racuna, jer je isti signal kao kod brojevi_razlika.
    _kazne_flag = {"leak": 5.0, "kraj_u_tagu": 3.0, "ratio_nizak": 3.0,
                   "p_gubitak": 2.0}
    _kazne_kod = {"en_ostaci": 3.0, "imena_nedostaju": 2.0,
                  "brojevi_razlika": 2.0}
    _derived = 10.0
    for _f in flags:
        _derived -= _kazne_flag.get(_f, 0.0)
    for _c in out.get("kodovi", []):
        _derived -= _kazne_kod.get(_c, 0.0)
    out["accuracy_derived"] = round(max(1.0, _derived), 1)
    out["flags"] = flags
    return out
'''

src = open(PUTANJA, encoding="utf-8").read()
n = src.count(STARO)
print(f"Pojavljivanja STARO: {n}")
if n != 1:
    print("STOP: ocekivano tacno 1, nista nije izmijenjeno")
    sys.exit(1)

poz = src.index(STARO)
pocetak = src.index("def accuracy_shadow")
kraj = src.index("def _plain_za_provjeru")
if not (pocetak < poz < kraj):
    print("STOP: STARO nije unutar accuracy_shadow")
    sys.exit(1)

open(PUTANJA, "w", encoding="utf-8").write(src.replace(STARO, NOVO, 1))
print("Izmjena upisana")
PYEOF
RC=$?
if [ $RC -ne 0 ]; then
    echo "PRIMJENA PALA -> vracam backup"
    cp "$BAK" core/metrics.py
    exit 1
fi

echo
echo "=== ast.parse + py_compile ==="
venv/bin/python3 -c "import ast; ast.parse(open('core/metrics.py', encoding='utf-8').read()); print('ast.parse OK')" \
  && venv/bin/python3 -m py_compile core/metrics.py && echo "py_compile OK"
RC=$?
if [ $RC -ne 0 ]; then
    echo "SINTAKSA PALA -> vracam backup"
    cp "$BAK" core/metrics.py
    exit 1
fi

echo
echo "=== T1: unit test accuracy_derived ==="
venv/bin/python3 << 'PYEOF'
import sys
from core.metrics import accuracy_shadow

slucajevi = [
    ("A cist blok",
     "<p>Ovo je obican tekst koji ima nekoliko rijeci u sebi.</p>",
     "<p>This is plain text that has several words in it.</p>", 10.0),
    ("B leak bez EN",
     "<p>Tekst { „korektura</p>", None, 5.0),
    ("C kraj_u_tagu bez EN",
     "<p>Tekst <em", None, 7.0),
    ("D leak + kraj_u_tagu + brojevi_razlika",
     "<p>Tekst { „korektura <em",
     "<p>Text 5 apples</p>", 1.0),
]

ok = True
for naziv, hr, en, ocekivano in slucajevi:
    r = accuracy_shadow(hr, en)
    d = r.get("accuracy_derived")
    status = "OK" if d == ocekivano else "GRESKA"
    if d != ocekivano:
        ok = False
    print(f"{status}  {naziv}: flags={r['flags']} kodovi={r.get('kodovi')} "
          f"derived={d} (ocekivano {ocekivano})")

print()
print("T1 PROSAO" if ok else "T1 PAO")
sys.exit(0 if ok else 1)
PYEOF
RC=$?
if [ $RC -ne 0 ]; then
    echo "T1 PAO -> vracam backup"
    cp "$BAK" core/metrics.py
    exit 1
fi

echo
echo "=== git diff --stat ==="
git diff --stat
echo
echo "KORAK 1 GOTOV. Nije commitovano. Sljedece: Korak 2 (pipeline.py)."
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
