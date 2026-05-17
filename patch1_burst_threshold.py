#!/usr/bin/env python3
"""
PATCH 1: burst_exhausted prag 3 → 15
Fajl: network/quota_tracker.py

PROBLEM:
  burst_exhausted se aktivira nakon samo 3× HTTP 429 u istom danu.
  Normalni RPM throttling (npr. 15 req/min Gemini free tier) lako okine
  3 bursta unutar minute — i ključ dobije 20h cooldown umjesto kratke pauze.

ISPRAVKA:
  Prag podignuti na 15. Na taj način samo prava dnevna iscrpljenost (>=15
  429-ova zaredom) okida dnevni cooldown, a kratkotrajni RPM bursti
  ostaju na kratkom cooldownu iz Retry-After headera.
"""

import re
import sys
from pathlib import Path

TARGET = Path("network/quota_tracker.py")

OLD = "        burst_exhausted = (self._daily_429_count >= 3)"
NEW = "        burst_exhausted = (self._daily_429_count >= 15)  # PATCH1: prag 3→15"


def apply(root: Path = Path(".")):
    path = root / TARGET
    if not path.exists():
        print(f"[PATCH1] ❌  Fajl nije nađen: {path}")
        sys.exit(1)

    src = path.read_text(encoding="utf-8")

    if NEW.strip() in src:
        print("[PATCH1] ✅  Već primijenjeno — preskačem.")
        return

    if OLD not in src:
        print("[PATCH1] ❌  Stari kod nije nađen. Provjeri ručno:")
        print(f"         Traži: {OLD!r}")
        sys.exit(1)

    patched = src.replace(OLD, NEW, 1)
    path.write_text(patched, encoding="utf-8")
    print(f"[PATCH1] ✅  Primijenjeno: burst_exhausted prag 3 → 15  ({path})")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    apply(root)
