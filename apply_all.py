#!/usr/bin/env python3
"""
apply_all.py — Primijeni sve 4 ispravke iz dijagnoze

Koristiti iz root direktorija projekta (Skriptorij/):
  python patches/apply_all.py
  python patches/apply_all.py /putanja/do/Skriptorij

Ispravke:
  PATCH 1 — burst_exhausted prag 3 → 15         (quota_tracker.py)
  PATCH 2 — RPM vs RPD cooldown razdvojen        (quota_tracker.py)
  PATCH 3 — Direktni Google URL fallback          (provider_urls.py + http_client.py)
  PATCH 4 — Token tracking: Gemini usageMetadata  (rate_limiter.py)

Svaki patch je idempotent — može se pokrenuti više puta bezopasno.
"""

import sys
import importlib.util
from pathlib import Path


def load_patch(patch_file: Path):
    spec = importlib.util.spec_from_file_location(patch_file.stem, patch_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    patches_dir = Path(__file__).parent
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    print(f"\n{'='*60}")
    print(f"  SKRIPTORIJ PATCH — primjena 4 ispravke")
    print(f"  Root: {root.resolve()}")
    print(f"{'='*60}\n")

    patches = [
        ("PATCH 1 — burst_exhausted prag",         "patch1_burst_threshold.py"),
        ("PATCH 2 — RPM/RPD cooldown razdvojen",    "patch2_rpm_cooldown.py"),
        ("PATCH 3 — Google direktni URL fallback",  "patch3_google_direct_fallback.py"),
        ("PATCH 4 — Token tracking Gemini fix",     "patch4_token_tracking.py"),
    ]

    failed = []
    for label, filename in patches:
        print(f"── {label}")
        patch_path = patches_dir / filename
        if not patch_path.exists():
            print(f"   ❌  Patch fajl nije nađen: {patch_path}")
            failed.append(label)
            continue
        try:
            mod = load_patch(patch_path)
            mod.apply(root)
        except SystemExit as e:
            if e.code != 0:
                failed.append(label)
        except Exception as ex:
            print(f"   ❌  Neočekivana greška: {ex}")
            failed.append(label)
        print()

    print(f"{'='*60}")
    if failed:
        print(f"  ❌  NEUSPJEŠNO: {len(failed)}/{len(patches)} patcheva")
        for f in failed:
            print(f"     • {f}")
        sys.exit(1)
    else:
        print(f"  ✅  SVE {len(patches)} ISPRAVKE PRIMIJENJENE USPJEŠNO")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
