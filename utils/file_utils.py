

"""Pomoćne funkcije — file utilities."""
import os
import re
from typing import Optional


def secure_filename(filename: str) -> str:
    """Sigurno ime fajla s podrškom za balkanska slova."""
    if not filename:
        return "nepoznato.epub"
    zamjene = {
        "č": "c", "ć": "c", "ž": "z", "š": "s", "đ": "dj",
        "Č": "C", "Ć": "C", "Ž": "Z", "Š": "S", "Đ": "Dj", " ": "_",
    }
    for d, e in zamjene.items():
        filename = filename.replace(d, e)
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9_.\-]", "_", filename)
    filename = re.sub(r"_+", "_", filename)
    return filename.strip("._-") or "knjiga.epub"


def safe_path(filename: str, root: Optional[str] = None) -> str:
    """Vraća sigurnu apsolutnu putanju unutar root direktorija."""
    from config.settings import PROJECTS_ROOT

    base = root or PROJECTS_ROOT
    safe = secure_filename(filename)
    full = os.path.realpath(os.path.join(base, safe))
    if not full.startswith(os.path.realpath(base)):
        raise ValueError(f"Path traversal pokušaj: {filename}")
    return full



