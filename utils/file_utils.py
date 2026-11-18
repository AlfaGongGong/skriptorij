"""Pomoćne funkcije — file utilities."""

import os
import re


def secure_filename(filename: str) -> str:
    """Sigurno ime fajla s podrškom za balkanska slova."""
    if not filename:
        return "nepoznato.epub"
    zamjene = {
        "č": "c",
        "ć": "c",
        "ž": "z",
        "š": "s",
        "đ": "dj",
        "Č": "C",
        "Ć": "C",
        "Ž": "Z",
        "Š": "S",
        "Đ": "Dj",
        " ": "_",
    }
    for d, e in zamjene.items():
        filename = filename.replace(d, e)
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9_.\-]", "_", filename)
    filename = re.sub(r"_+", "_", filename)
    return filename.strip("._-") or "knjiga.epub"


def safe_path(filename: str, root: str | None = None) -> str:
    """Vraća sigurnu apsolutnu putanju unutar root direktorija."""
    from config.settings import PROJECTS_ROOT

    base = root or PROJECTS_ROOT
    safe = secure_filename(filename)
    full = os.path.realpath(os.path.join(base, safe))
    if not full.startswith(os.path.realpath(base)):
        raise ValueError(f"Path traversal pokušaj: {filename}")
    return full


def atomic_write_text(path, content: str) -> None:
    """Atomicki upis: pise u .tmp pa os.replace. Prezivljava pad usred upisa."""
    from pathlib import Path as _P
    path = _P(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import threading as _th
    tmp = path.with_name("%s.%d.%d.tmp" % (path.name, os.getpid(), _th.get_ident()))
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_json(path, data, indent: int = 2) -> None:
    """Atomicki JSON upis sa indent + ensure_ascii=False."""
    import json
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False))
