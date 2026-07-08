#!/usr/bin/env python3
"""
project_snapshot.py — Generira kompaktan AI-kontekst snapshot projekta.

Upotreba:
    python project_snapshot.py [root_dir] [opcije]

Opcije:
    --out FILE        Izlazna datoteka (default: snapshot.txt)
    --max-lines N     Maks. redova po datoteci (default: 80)
    --max-kb N        Preskoči datoteke veće od N KB (default: 100)
    --no-tree         Ne prikazuj stablo direktorija
    --ext a,b,c       Prikaži samo ove ekstenzije (npr. py,js,html)
    --skip-dirs d,e   Dodatni direktoriji za preskakanje
    --stats           Prikaži statistiku na kraju
    --help            Ova poruka

Primjer:
    python project_snapshot.py ~/booklyfi --out ctx.txt --max-lines 60
"""

import os
import sys
import argparse
import textwrap
from pathlib import Path
from datetime import datetime

# ── Defaultni skip-listi ────────────────────────────────────────────────────
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", "dist", "build", "eggs", ".eggs",
    "*.egg-info", ".tox", "htmlcov", ".coverage", "site-packages",
    "migrations", ".idea", ".vscode", "tmp", "temp", "logs", "log",
    ".cache", "uploads", "instance",
}

SKIP_EXTENSIONS = {
    # Binaries / media
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".ogg", ".avi", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".db", ".sqlite", ".sqlite3",
    ".lock",  # poetry.lock, package-lock.json — prevelike
    ".map",   # source maps
    ".min.js", ".min.css",
}

# Datoteke koje su uvijek zanimljive bez obzira na ekstenziju
ALWAYS_INCLUDE_NAMES = {
    "readme.md", "readme.rst", "readme.txt",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "makefile", "procfile",
    "package.json",  # bez node_modules naravno
    "config.py", "settings.py", "wsgi.py", "asgi.py",
}

# Ekstenzije koje prikazujemo s punim sadržajem (do max_lines)
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm",
    ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".sh", ".bash", ".zsh", ".fish",
    ".md", ".rst", ".txt",
    ".sql", ".jinja", ".jinja2", ".j2",
    ".xml", ".csv",
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Generira AI-kontekst snapshot projekta.",
        add_help=False,
    )
    p.add_argument("root", nargs="?", default=".", help="Root direktorij projekta")
    p.add_argument("--out", default="snapshot.txt", help="Izlazna datoteka")
    p.add_argument("--max-lines", type=int, default=80, metavar="N",
                   help="Maks. redova po datoteci (default: 80)")
    p.add_argument("--max-kb", type=int, default=100, metavar="N",
                   help="Preskoči datoteke veće od N KB (default: 100)")
    p.add_argument("--no-tree", action="store_true", help="Ne prikazuj stablo")
    p.add_argument("--ext", default="", metavar="a,b",
                   help="Prikaži samo ove ekstenzije (bez točke, csv)")
    p.add_argument("--skip-dirs", default="", metavar="d,e",
                   help="Dodatni direktoriji za preskakanje")
    p.add_argument("--stats", action="store_true", help="Prikaži statistiku")
    p.add_argument("--help", action="store_true")
    return p.parse_args()


# ── Stablo direktorija ───────────────────────────────────────────────────────

def build_tree(root: Path, skip: set, max_depth: int = 6, prefix="") -> list[str]:
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return lines

    entries = [e for e in entries if e.name not in skip and not e.name.startswith(".")]

    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir() and max_depth > 0:
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(build_tree(entry, skip, max_depth - 1, prefix + extension))
    return lines


# ── Čitanje datoteke ─────────────────────────────────────────────────────────

def read_file_snippet(path: Path, max_lines: int, max_kb: int) -> tuple[str, bool]:
    """Vraća (sadržaj, truncated). Truncated=True ako je odrezan."""
    size_kb = path.stat().st_size / 1024
    if size_kb > max_kb:
        return f"[PRESKOČENO — veličina {size_kb:.0f} KB > {max_kb} KB]", False

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[GREŠKA PRI ČITANJU: {e}]", False

    lines = text.splitlines()
    truncated = len(lines) > max_lines
    snippet = "\n".join(lines[:max_lines])
    return snippet, truncated


# ── Glavni collector ─────────────────────────────────────────────────────────

def collect_files(root: Path, skip_dirs: set, only_exts: set,
                  max_kb: int) -> list[Path]:
    collected = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filtriraj direktorije in-place (os.walk respektira izmjene)
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not d.startswith(".")
        ]
        dirnames.sort()

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()
            name_lower = fname.lower()

            # Uvijek uključi posebne datoteke
            if name_lower in ALWAYS_INCLUDE_NAMES:
                collected.append(fpath)
                continue

            # Preskočeni tipovi
            if ext in SKIP_EXTENSIONS:
                continue
            if fname.endswith(".min.js") or fname.endswith(".min.css"):
                continue

            # Filter po ekstenziji
            if only_exts and ext.lstrip(".") not in only_exts:
                continue

            if ext in CODE_EXTENSIONS:
                collected.append(fpath)

    return collected


# ── Formatiranje izlaza ──────────────────────────────────────────────────────

SEPARATOR = "═" * 72

def format_header(root: Path) -> str:
    return (
        f"{SEPARATOR}\n"
        f"  PROJECT SNAPSHOT — {root.resolve().name}\n"
        f"  Generirano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  Root: {root.resolve()}\n"
        f"{SEPARATOR}\n"
    )


def format_file_block(path: Path, root: Path, content: str, truncated: bool,
                      max_lines: int) -> str:
    rel = path.relative_to(root)
    size_kb = path.stat().st_size / 1024
    header = f"\n── FILE: {rel}  [{size_kb:.1f} KB]\n"
    footer = f"\n[... odrezano na {max_lines} redova ...]\n" if truncated else ""
    lang = path.suffix.lstrip(".")
    return f"{header}```{lang}\n{content}\n```{footer}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.help:
        print(__doc__)
        sys.exit(0)

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"❌ Direktorij ne postoji: {root}")
        sys.exit(1)

    # Sklopi skip set
    skip_dirs = SKIP_DIRS.copy()
    if args.skip_dirs:
        skip_dirs.update(d.strip() for d in args.skip_dirs.split(",") if d.strip())

    # Ekstenzijski filter
    only_exts: set[str] = set()
    if args.ext:
        only_exts = {e.strip().lstrip(".") for e in args.ext.split(",") if e.strip()}

    out_path = Path(args.out)
    parts: list[str] = []

    # 1. Header
    parts.append(format_header(root))

    # 2. Stablo
    if not args.no_tree:
        tree_lines = build_tree(root, skip_dirs)
        parts.append("STRUKTURA PROJEKTA:\n")
        parts.append(root.name + "/\n")
        parts.append("\n".join(tree_lines))
        parts.append(f"\n\n{SEPARATOR}\n")

    # 3. Sadržaj datoteka
    files = collect_files(root, skip_dirs, only_exts, args.max_kb)

    if not files:
        parts.append("\n[Nisu pronađene odgovarajuće datoteke.]\n")
    else:
        parts.append(f"DATOTEKE ({len(files)} ukupno):\n")
        for fpath in files:
            content, truncated = read_file_snippet(fpath, args.max_lines, args.max_kb)
            parts.append(format_file_block(fpath, root, content, truncated, args.max_lines))

    # 4. Statistika
    if args.stats:
        total_size = sum(f.stat().st_size for f in files if f.exists()) / 1024
        parts.append(f"\n\n{SEPARATOR}\n")
        parts.append(f"STATISTIKA:\n")
        parts.append(f"  Datoteka: {len(files)}\n")
        parts.append(f"  Ukupno (čitljivo): {total_size:.1f} KB\n")
        parts.append(f"  Max redova/datoteci: {args.max_lines}\n")
        parts.append(f"  Max veličina/datoteci: {args.max_kb} KB\n")

    # 5. Zapis
    output = "\n".join(parts)
    out_path.write_text(output, encoding="utf-8")

    # Terminal info
    out_kb = out_path.stat().st_size / 1024
    # Gruba procjena tokena (1 token ≈ 4 znaka)
    approx_tokens = int(out_path.stat().st_size / 4)

    print(f"✅ Snapshot: {out_path.resolve()}")
    print(f"   Datoteka: {len(files)}")
    print(f"   Veličina: {out_kb:.1f} KB")
    print(f"   ~Tokeni:  {approx_tokens:,} (gruba procjena)")
    print()
    print("💡 Savjeti za manji kontekst:")
    print(f"   --max-lines 40   (trenutno: {args.max_lines})")
    print(f"   --ext py,js,html (samo određene ekstenzije)")
    print(f"   --skip-dirs static,templates (preskoči foldere)")


if __name__ == "__main__":
    main()
