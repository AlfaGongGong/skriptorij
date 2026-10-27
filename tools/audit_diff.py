#!/usr/bin/env python3
"""Uporedi dva audit JSON-a."""
import json
import sys
from pathlib import Path

BASELINE_DIR = Path("/storage/emulated/0/Download/audit_baselines")
CURRENT = Path("/storage/emulated/0/Download/pipeline_audit_full.json")

if len(sys.argv) >= 3:
    baseline, current = Path(sys.argv[1]), Path(sys.argv[2])
elif len(sys.argv) == 2:
    baseline, current = Path(sys.argv[1]), CURRENT
else:
    if not BASELINE_DIR.exists():
        print("Nema baseline direktorija. Pokreni: make baseline"); sys.exit(0)
    bl = sorted(BASELINE_DIR.glob("baseline_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not bl:
        print("Nema baseline-a. Pokreni: make baseline"); sys.exit(0)
    baseline, current = bl[0], CURRENT

if not baseline.exists():
    print(f"Baseline ne postoji: {baseline}"); sys.exit(0)
if not current.exists():
    print(f"Trenutni: {current} ne postoji. Pokreni: make audit-full"); sys.exit(0)

b = json.load(baseline.open(encoding="utf-8"))
c = json.load(current.open(encoding="utf-8"))
bc, cc = b.get("counts", {}), c.get("counts", {})

print(f"Baseline: {baseline.name}")
print(f"Trenutni: {current.name}")
print(f"\nFAIL: {bc.get('FAIL', 0)} → {cc.get('FAIL', 0)}")
print(f"WARN: {bc.get('WARN', 0)} → {cc.get('WARN', 0)}")
print(f"OK:   {bc.get('OK', 0)}   → {cc.get('OK', 0)}")

def key(f): return (f.get("level"), f.get("phase"), f.get("msg", "")[:80])
bf = {key(f) for f in b.get("findings", [])}
cf = {key(f) for f in c.get("findings", [])}
nf = sorted([k for k in cf - bf if k[0] == "FAIL"])
fx = sorted([k for k in bf - cf if k[0] == "FAIL"])

print(f"\nNovi FAIL ({len(nf)}):")
for _, p_, m in nf[:20]: print(f"  [{p_}] {m}")
print(f"\nRešeni FAIL ({len(fx)}):")
for _, p_, m in fx[:20]: print(f"  [{p_}] {m}")

sys.exit(1 if nf else 0)
