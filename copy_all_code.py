#!/usr/bin/env python3
"""
copy_all_code.py — Sakuplja sav tekstualni kod iz projekta
i generiše jedinstveni txt fajl sa file tree + sadržajem svih fajlova.
Preskaču se direktorijumi poput node_modules, venv, build, itd.
"""

import os
import sys
import fnmatch
from pathlib import Path
from datetime import datetime

# ── Podešavanja ────────────────────────────────────────────────────────────────
# Direktorijumi koji se potpuno preskaču (i u stablu i pri sakupljanju fajlova)
SKIP_DIRS = {
    "__pycache__",
    "venv", ".venv", "env", ".env",
    ".git", ".idea", ".vscode",
    "node_modules", "bower_components",
    "build", "dist", "target", "out",
    "coverage", ".tox", ".pytest_cache",
    "docs/_build",           # Sfinks / MkDocs build
    "site",                  # često statički build
    "data",                  # u originalu
    "_skr_*",                # pattern: svi direktorijumi koji počinju sa "_skr_"
    "tts_radni_folder",
    "fix_backup_*",          # pattern: direktorijumi sa prefiksom "fix_backup_"
    "*.egg-info",            # Python egg-info dirs
}

# Fajlovi koji se uvek preskaču
SKIP_FILES = {
    "*.pyc", "*.pyo",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.svg", "*.ico",
    "*.epub", "*.mobi", "*.ttsfilter",
    "*.db", "*.sqlite", "*.sqlite3",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
    "*.zip", "*.tar", "*.gz", "*.7z", "*.rar",
    "*.mp3", "*.mp4", "*.webm", "*.ogg",
    "*.pdf", "*.doc", "*.docx",
    "*.log",                 # log fajlovi
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",  # lock fajlovi
}

# Dozvoljene ekstenzije (tekstualni fajlovi)
TEXT_EXTENSIONS = {
    ".py", ".html", ".css", ".js", ".json", ".md", ".txt", ".sh",
    ".yml", ".yaml", ".ini", ".cfg", ".toml", ".xml", ".xhtml",
    ".csv", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
    ".bat", ".ps1", ".zsh", ".fish",
}

# Dozvoljeni fajlovi bez ekstenzije (npr. Dockerfile, Makefile)
ALLOWED_NO_EXT = {"Dockerfile", "Makefile", "LICENSE", "requirements.txt"}

MAX_FILE_SIZE_BYTES = 1_000_000  # 1 MB

# ── Output ─────────────────────────────────────────────────────────────────────
OUTPUT_FILE = f"PROJEKAT_KOMPLETAN_KOD_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# ── Pomoćne funkcije za preskakanje ────────────────────────────────────────────
def _matches_pattern(name, pattern):
    """Proverava da li ime fajla/dir odgovara glob patternu (jednostavno)."""
    if pattern.endswith("/*"):
        prefix = pattern[:-1]  # npr. "fix_backup_"
        return name.startswith(prefix)
    elif pattern.startswith("*."):
        ext = pattern[1:]  # npr. ".pyc"
        return name.endswith(ext)
    # Opšti glob pattern
    return fnmatch.fnmatch(name, pattern)

def should_skip_dir(dir_name):
    """Vraća True ako direktorijum treba preskočiti."""
    for d in SKIP_DIRS:
        if _matches_pattern(dir_name, d):
            return True
    return False

def should_skip_file(file_name):
    """Vraća True ako fajl treba preskočiti."""
    for f in SKIP_FILES:
        if _matches_pattern(file_name, f):
            return True
    return False

def is_text_file(file_name):
    """Proverava da li je fajl dozvoljen na osnovu ekstenzije ili posebnog imena."""
    ext = os.path.splitext(file_name)[1].lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if file_name in ALLOWED_NO_EXT:
        return True
    return False

# ── Tree generator ─────────────────────────────────────────────────────────────
def generate_tree(root_dir, prefix=""):
    """Rekurzivno generiše string file tree-a (samo relevantni fajlovi i folderi)."""
    lines = []
    try:
        entries = sorted(os.listdir(root_dir))
    except PermissionError:
        return [prefix + "└── [PERMISSION DENIED]"]

    dirs = []
    files = []
    for entry in entries:
        full = os.path.join(root_dir, entry)
        if os.path.isdir(full):
            if not should_skip_dir(entry):
                dirs.append(entry)
        else:
            if not should_skip_file(entry) and is_text_file(entry):
                try:
                    size = os.path.getsize(full)
                    if size <= MAX_FILE_SIZE_BYTES:
                        files.append(entry)
                except OSError:
                    pass

    all_items = dirs + files
    for i, item in enumerate(all_items):
        is_last = (i == len(all_items) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + item)
        if item in dirs:
            full = os.path.join(root_dir, item)
            extension = "    " if is_last else "│   "
            lines.extend(generate_tree(full, prefix + extension))
    return lines

# ── Sakupljanje fajlova ────────────────────────────────────────────────────────
def collect_files(root_dir):
    """Sakuplja listu (apsolutna_putanja, relativna_putanja) za sve dozvoljene tekstualne fajlove."""
    file_list = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Preskoči zabranjene direktorijume in-place
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for fname in filenames:
            if should_skip_file(fname):
                continue
            if not is_text_file(fname):
                continue
            full = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(full) > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(full, root_dir)
            file_list.append((full, rel))
    return sorted(file_list, key=lambda x: x[1])

# ── Glavna funkcija ────────────────────────────────────────────────────────────
def main():
    root = Path.cwd()
    print(f"📁 Skeniram: {root}")

    # 1. File tree
    tree_lines = generate_tree(root)
    tree_str = "\n".join(tree_lines) if tree_lines else "(prazan direktorijum)"

    # 2. Sadržaj fajlova
    files = collect_files(root)
    code_blocks = []
    for full, rel in files:
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception as e:
            content = f"[GREŠKA PRI ČITANJU: {e}]"
        code_blocks.append(
            f"================================================================================\n"
            f"FAJL: {rel}\n"
            f"================================================================================\n\n"
            f"{content}\n\n"
            f"KRAJ FAJLA: {rel}\n"
        )

    # 3. Spajanje
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final = (
        f"================================================================================\n"
        f"PROJEKAT: KOMPLETAN IZVORNI KOD\n"
        f"================================================================================\n"
        f"Datum generisanja: {now}\n"
        f"Broj fajlova: {len(files)}\n"
        f"================================================================================\n\n"
        f"================================================================================\n"
        f"FILE TREE (struktura projekta)\n"
        f"================================================================================\n"
        f"{tree_str}\n\n"
        f"================================================================================\n"
        f"SADRŽAJ FAJLOVA\n"
        f"================================================================================\n\n"
        + "\n".join(code_blocks)
    )

    out_path = root / OUTPUT_FILE
    out_path.write_text(final, encoding="utf-8")
    print(f"✅ Završeno! Izlazni fajl: {out_path}")
    print(f"   Ukupno fajlova: {len(files)}")

if __name__ == "__main__":
    main()