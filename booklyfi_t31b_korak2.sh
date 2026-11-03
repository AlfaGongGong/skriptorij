#!/bin/bash
# T3.1b Korak 2: min(LLM, accuracy_derived) u processing/pipeline.py
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t31b_korak2_$TS.log"
BAK=".logs/pipeline_backup_$TS.py"

{
echo "=== HEAD ==="
git log --oneline -1
grep -c "accuracy_derived" core/metrics.py | sed 's/^/accuracy_derived u metrics.py: /'

cp processing/pipeline.py "$BAK" || { echo "BACKUP NEUSPJEO"; exit 1; }
echo "Backup: $BAK"

echo
echo "=== PRIMJENA ==="
venv/bin/python3 << 'PYEOF'
import sys

PUTANJA = "processing/pipeline.py"

IZMJENE = [
# E1: _acc = {} prije try
(
'''    try:
        from core.metrics import accuracy_shadow
''',
'''    _acc = {}
    try:
        from core.metrics import accuracy_shadow
''',
),
# E2: pomocna funkcija _cap_acc poslije accuracy_shadow bloka
(
'''        logger.exception("[T3.2] accuracy shadow Exception")

    if je_paratekst:
''',
'''        logger.exception("[T3.2] accuracy shadow Exception")

    # 2026-11-01 T3.1b: konacna ocjena = min(LLM, accuracy_derived).
    # LLM scorer ne vidi EN; check_accuracy vidi. Kad se ne slazu,
    # vjerujemo determinističkom. _acc je {} ako je shadow pao -> bez capa.
    def _cap_acc(_s):
        _d = _acc.get("accuracy_derived") if isinstance(_acc, dict) else None
        if _d is not None and _d < _s:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ accuracy cap "
                f"{_s:.1f} -> {_d:.1f} (flags={_acc.get('flags', [])})",
                "warning",
            )
            return _d
        return _s

    if je_paratekst:
''',
),
# E3: paratekst
(
'''        score_float = 8.5
        self._quality_scores[stem_key] = score_float
''',
'''        score_float = _cap_acc(8.5)
        self._quality_scores[stem_key] = score_float
''',
),
# E4: nonprose
(
'''            score_float = 10.0
            self._quality_scores[stem_key] = score_float
''',
'''            score_float = _cap_acc(10.0)
            self._quality_scores[stem_key] = score_float
''',
),
# E5: glavna grana, poslije ratio cap-ova
(
'''        preview = BeautifulSoup(finalno, "html.parser").get_text()[:80]
        self._quality_scores[stem_key] = score_float
''',
'''        score_float = _cap_acc(score_float)

        preview = BeautifulSoup(finalno, "html.parser").get_text()[:80]
        self._quality_scores[stem_key] = score_float
''',
),
]

src = open(PUTANJA, encoding="utf-8").read()
for i, (staro, novo) in enumerate(IZMJENE, 1):
    n = src.count(staro)
    print(f"E{i}: pojavljivanja STARO = {n}")
    if n != 1:
        print("STOP: ocekivano tacno 1, nista nije upisano")
        sys.exit(1)

pocetak = src.index("async def _quality_scoring(")
kraj = src.index("\nasync def ", pocetak + 10) if "\nasync def " in src[pocetak + 10:] else len(src)
for i, (staro, novo) in enumerate(IZMJENE, 1):
    poz = src.index(staro)
    if not (pocetak < poz):
        print(f"STOP: E{i} je prije _quality_scoring")
        sys.exit(1)

for staro, novo in IZMJENE:
    src = src.replace(staro, novo, 1)

open(PUTANJA, "w", encoding="utf-8").write(src)
print("Sve izmjene upisane")
PYEOF
RC=$?
if [ $RC -ne 0 ]; then
    echo "PRIMJENA PALA -> vracam backup"
    cp "$BAK" processing/pipeline.py
    exit 1
fi

echo
echo "=== ast.parse + py_compile ==="
venv/bin/python3 -c "import ast; ast.parse(open('processing/pipeline.py', encoding='utf-8').read()); print('ast.parse OK')" \
  && venv/bin/python3 -m py_compile processing/pipeline.py && echo "py_compile OK"
RC=$?
if [ $RC -ne 0 ]; then
    echo "SINTAKSA PALA -> vracam backup"
    cp "$BAK" processing/pipeline.py
    exit 1
fi

echo
echo "=== _cap_acc pojavljivanja (ocekivano 4: 1 def + 3 poziva) ==="
grep -n "_cap_acc" processing/pipeline.py

echo
echo "=== T: _quality_scoring sa lazim self (paratekst grana, bez LLM-a) ==="
venv/bin/python3 << 'PYEOF'
import sys, asyncio, types
from pathlib import Path

try:
    from processing.pipeline import _quality_scoring
except Exception as e:
    print(f"IMPORT PAO: {e!r}")
    sys.exit(1)

ck = Path(".logs/t31b_k2_ck")
ck.mkdir(parents=True, exist_ok=True)
logovi = []

def napravi_self():
    s = types.SimpleNamespace()
    s.shared_stats = {}
    s.checkpoint_dir = ck
    s.log = lambda msg, lvl="info": logovi.append((lvl, msg))
    s._atomic_write = lambda p, t: Path(p).write_text(t, encoding="utf-8")
    return s

slucajevi = [
    ("leak blok (paratekst 8.5 -> cap 5.0)",
     "<p>Tekst { „korektura</p>", "<p>Text</p>", 5.0),
    ("cist blok (paratekst 8.5 ostaje)",
     "<p>Ovo je obican tekst koji ima nekoliko rijeci u sebi.</p>",
     "<p>This is plain text that has several words in it.</p>", 8.5),
]

ok = True
for naziv, hr, en, ocek in slucajevi:
    s = napravi_self()
    asyncio.run(_quality_scoring(s, hr, en, 0, "toc_test", "tip", "prov",
                                 tip_ocjenjivanja="prevod"))
    dobijeno = s._quality_scores.get("toc_test_blok_0")
    st = "OK" if dobijeno == ocek else "GRESKA"
    if dobijeno != ocek:
        ok = False
    print(f"{st}  {naziv}: score={dobijeno} (ocekivano {ocek})")

print("\nLogovi capa:")
for l in logovi:
    if "accuracy cap" in l[1]:
        print(f"  [{l[0]}] {l[1]}")

print("\nT PROSAO" if ok else "\nT PAO")
sys.exit(0 if ok else 1)
PYEOF
RC=$?
if [ $RC -ne 0 ]; then
    echo "TEST PAO -> vracam backup pipeline.py (metrics.py ostaje)"
    cp "$BAK" processing/pipeline.py
    exit 1
fi

echo
echo "=== git diff --stat ==="
git diff --stat
echo
echo "KORAK 2 GOTOV. Nije commitovano."
echo "Sljedece: T3 regresija na TWOC_test_3pogl + make audit-quick, pa commit."
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
