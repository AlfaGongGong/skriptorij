#!/usr/bin/env python3
"""Omotac: kod je u core/apply_overlay.py (R9-27). Upotreba ostaje: apply_overlay.py <ck_dir> <overlay_json> [--strict] [--dry]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.apply_overlay import main, primijeni  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main(sys.argv))
