# utils/checkpoint_cleaner.py
import random
from pathlib import Path

def _no_cisti_chk_fajlove(checkpoint_dir: Path, log_fn=None) -> int:
    if not checkpoint_dir.exists():
        return 0
    popravljeno = 0
    for chk in checkpoint_dir.glob("*.chk"):
        try:
            sadrzaj = chk.read_text("utf-8", errors="ignore")
            # jednostavno čišćenje – možete dodati _cisti_json_wrapper
            if sadrzaj.startswith("{"):
                # već ok
                pass
        except: pass
    return popravljeno
