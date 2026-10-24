#!/usr/bin/env python3
"""
Backfill quality_metrics.json iz postojecih .chk fajlova.
Deterministicki, ne poziva AI. Idempotentan.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/root/skriptorij")
from config.settings import CHECKPOINT_BASE_DIR
from core.metrics import classify_metrics, compute_metrics


def backfill_one(checkpoints_dir: Path) -> dict:
    mp = checkpoints_dir / "quality_metrics.json"
    existing = {}
    if mp.exists():
        try:
            existing = json.loads(mp.read_text("utf-8"))
        except Exception:
            existing = {}

    chks = sorted(checkpoints_dir.glob("*.chk"))
    added = skipped = errors = 0
    for chk in chks:
        stem = chk.stem
        if stem in existing:
            skipped += 1
            continue
        try:
            txt = chk.read_text("utf-8", errors="ignore")
            m = compute_metrics(txt)
            m["quality_class"] = classify_metrics(m)
            existing[stem] = m
            added += 1
        except Exception:
            errors += 1

    if added > 0:
        mp.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "total": len(existing),
    }


def main():
    print("=" * 70)
    print("BACKFILL quality_metrics.json")
    print("=" * 70)
    if not CHECKPOINT_BASE_DIR.exists():
        print(f"CHECKPOINT_BASE_DIR ne postoji: {CHECKPOINT_BASE_DIR}")
        return 1

    ta = ts = te = 0
    for proj in sorted(CHECKPOINT_BASE_DIR.glob("_skr_*")):
        ck = proj / "checkpoints"
        if not ck.exists():
            continue
        chks = list(ck.glob("*.chk"))
        if not chks:
            continue
        print(f"{proj.name[:60]}")
        print(f"  .chk fajlova: {len(chks)}")
        s = backfill_one(ck)
        print(
            f"  added: {s['added']}, skipped: {s['skipped']}, errors: {s['errors']}, total: {s['total']}"
        )
        print()
        ta += s["added"]
        ts += s["skipped"]
        te += s["errors"]

    print("=" * 70)
    print(f"UKUPNO: added={ta}, skipped={ts}, errors={te}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
