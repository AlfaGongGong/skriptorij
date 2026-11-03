#!/bin/bash
# TWOC: zasto su blokovi nisko ocijenjeni (samo citanje)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_zasto_nisko_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
venv/bin/python3 << 'PYEOF'
import os, re, json, glob
from collections import Counter

CK = os.environ["CK"]
ld = lambda f: json.load(open(f"{CK}/{f}", encoding="utf-8")) if os.path.exists(f"{CK}/{f}") else {}
sc = {k: float(v) for k, v in ld("quality_scores.json").items() if isinstance(v, (int, float))}
qa, qm = ld("quality_accuracy.json"), ld("quality_metrics.json")
sha = lambda t: re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
plain = lambda t: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
PROM = {"part0189.html_blok_2", "part0192.html_blok_6", "part0192.html_blok_8",
        "part0235.html_blok_0", "part0244.html_blok_0"}

def uzrok(k, s):
    a = qa.get(k, {})
    d, r = a.get("accuracy_derived"), a.get("ratio")
    if k in PROM and s == 6.0: return "PROMOCIJA (LEKTOR pao, prevod.chk 6.0)"
    if d is not None and abs(d - s) < 1e-9 and d < 10:
        return f"ACCURACY cap ({a.get('flags')} {a.get('kodovi')})"
    if isinstance(r, (int, float)) and ((r < .55 and s == 5.0) or (.55 <= r < .65 and s == 6.5) or (.65 <= r < .75 and s == 7.5)):
        return f"RATIO cap (ratio={r})"
    return "LLM scorer (stil/tecnost, bez deterministickog signala)"

nizak = sorted(((k, v) for k, v in sc.items() if v < 7.5 and os.path.exists(f"{CK}/{k}.chk")), key=lambda x: x[1])
print(f"\n=== 1. Blokova < 7.5: {len(nizak)} ===")
c = Counter(uzrok(k, v).split(" (")[0] for k, v in nizak)
print("  po uzroku:", dict(c))
print(f"  {'blok':<26}{'ocj':>5} {'deriv':>6} {'ratio':>6}  uzrok")
for k, v in nizak:
    a = qa.get(k, {})
    print(f"  {k:<26}{v:>5} {str(a.get('accuracy_derived','-')):>6} {str(a.get('ratio','-')):>6}  {uzrok(k, v)}")

print("\n=== 2. Sadrzaj najnize ocijenjenih (8) ===")
for k, v in nizak[:8]:
    t = plain(sha(open(f"{CK}/{k}.chk", encoding="utf-8", errors="replace").read()))
    pv = f"{CK}/{k}.prevod.chk"
    n_pv = len(plain(sha(open(pv, encoding="utf-8", errors="replace").read()))) if os.path.exists(pv) else None
    print(f"\n--- {k} | ocjena {v} | {len(t)} zn plain | prevod.chk plain: {n_pv}")
    print("  metrike:", json.dumps(qm.get(k, {}), ensure_ascii=False)[:400])
    print("  accuracy:", json.dumps(qa.get(k, {}), ensure_ascii=False)[:300])
    print("  POCETAK:", t[:260])
    print("  KRAJ   :", t[-160:])
    # opce znakove kvara u tekstu
    sumnje = {
        "EN stop-rijeci": len(re.findall(r"\b(?:the|and|was|with|that|have)\b", t)),
        "ASCII \"": t.count('"'),
        "dupli razmaci/tacke": len(re.findall(r"\.\.|\s,|\s\.", t)),
        "srpski oblici": len(re.findall(r"\b(?:preduzeti|saglasan|lepo|beo|videti)\b", t, re.I)),
        "'da' + prezent": len(re.findall(r"\b(?:uspio|pokušao|mogao|morao)\s+je\s+da\b", t)),
    }
    print("  sumnjivi znakovi:", {a: b for a, b in sumnje.items() if b})

print("\n=== 3. Zapisi u logovima (zasto je ocjena pala) ===")
import subprocess
for k, v in nizak[:8]:
    b = k.rsplit("_blok_", 1); fn, idx = b[0], b[1]
    r = subprocess.run(["grep", "-rIh", "-E", f"{re.escape(fn)}\\] Blok {idx}:|{re.escape(k)}",
                       ".logs", "/storage/emulated/0/Download"],
                       capture_output=True, text=True)
    red = [l for l in r.stdout.splitlines() if re.search(r"score|cap|accuracy|LEKTOR|KOREKTOR|ocjen", l, re.I)][-4:]
    print(f"--- {k}")
    for l in red: print("   ", l[:210])

print("\n=== 4. Raspodjela po poglavlju (gdje se ocjene skupljaju) ===")
po = {}
for k, v in sc.items():
    po.setdefault(k.split(".html")[0], []).append(v)
losi = sorted(((sum(x)/len(x), p, len(x)) for p, x in po.items() if len(x) >= 2))[:8]
for avg, p, n in losi:
    print(f"  {p}: prosjek {avg:.2f} ({n} blokova)")

print("\n=== 5. human_review ===")
print(json.dumps(ld("human_review.json"), ensure_ascii=False)[:600])
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
