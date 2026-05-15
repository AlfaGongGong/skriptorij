#!/usr/bin/env python3
"""
zipuj.py — Generiše file tree projekta i pravi arhivu izvornog koda.
Korišćenje: python zipuj.py [putanja_do_projekta]
"""

import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ── Konfiguracija ──────────────────────────────────────────────────────────────

EKSTENZIJE = {".py", ".json", ".js", ".css", ".html", ".txt", ".log"}

ISKLJUCI_DIREKTORIJUME = {
    "__pycache__", "node_modules", ".git", ".venv", "venv",
    "env", "dist", "build", ".idea", ".vscode", "backups",
    ".mypy_cache", ".pytest_cache", "htmlcov",
}

ISKLJUCI_FAJLOVE = {
    "dev_api.json", "api_state.json", "proxies.json",
}

ISKLJUCI_PREFIKSE = (
    "PROJEKAT_KOMPLETAN_KOD_",
    "skriptorij_",
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def treba_preskociti_dir(ime: str) -> bool:
    return ime in ISKLJUCI_DIREKTORIJUME or ime.startswith(".")

def treba_preskociti_fajl(putanja: Path) -> bool:
    if putanja.name in ISKLJUCI_FAJLOVE:
        return True
    for prefiks in ISKLJUCI_PREFIKSE:
        if putanja.name.startswith(prefiks):
            return True
    return False

# ── File tree ──────────────────────────────────────────────────────────────────

def generiši_tree(
    root: Path,
    trenutni: Path,
    prefix: str = "",
    linije: list[str] | None = None,
) -> list[str]:
    if linije is None:
        linije = [f"{root.name}/"]

    stavke = sorted(trenutni.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    vidljive = [s for s in stavke if not (s.is_dir() and treba_preskociti_dir(s.name))]

    for i, stavka in enumerate(vidljive):
        konektor = "└── " if i == len(vidljive) - 1 else "├── "
        produžetak = "    " if i == len(vidljive) - 1 else "│   "

        if stavka.is_dir():
            linije.append(f"{prefix}{konektor}{stavka.name}/")
            generiši_tree(root, stavka, prefix + produžetak, linije)
        else:
            marker = " ⚠️ [ISKLJUČEN IZ ZIPA]" if treba_preskociti_fajl(stavka) else ""
            linije.append(f"{prefix}{konektor}{stavka.name}{marker}")

    return linije

# ── Zip ───────────────────────────────────────────────────────────────────────

def napravi_zip(root: Path, ime_zipa: Path) -> tuple[int, int]:
    """Vraća (broj_fajlova, ukupna_veličina_bajta)."""
    broj = 0
    veličina = 0

    with zipfile.ZipFile(ime_zipa, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root):
            # Filtriraj direktorijume in-place (os.walk poštuje izmene)
            dirnames[:] = [d for d in dirnames if not treba_preskociti_dir(d)]

            for ime in sorted(filenames):
                putanja = Path(dirpath) / ime

                if treba_preskociti_fajl(putanja):
                    continue
                if putanja.suffix.lower() not in EKSTENZIJE:
                    continue

                arcname = putanja.relative_to(root.parent)
                zf.write(putanja, arcname)
                broj += 1
                veličina += putanja.stat().st_size

    return broj, veličina

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Odredi root projekta
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
    else:
        root = Path.cwd()

    if not root.is_dir():
        print(f"❌ Greška: '{root}' nije direktorijum.")
        sys.exit(1)

    danas = datetime.now().strftime("%d_%m_%Y")
    ime_zipa = root.parent / f"skriptorij_{danas}.zip"

    print(f"📁 Projekat : {root}")
    print(f"📦 Arhiva   : {ime_zipa}")
    print()

    # ── 1. Generiši file tree ──
    print("🌳 File tree projekta:")
    print("─" * 60)
    tree_linije = generiši_tree(root, root)
    tree_tekst = "\n".join(tree_linije)
    print(tree_tekst)
    print("─" * 60)
    print()

    # Sačuvaj tree kao txt (biće uključen u zip)
    tree_fajl = root / "file_tree.txt"
    tree_fajl.write_text(tree_tekst + "\n", encoding="utf-8")
    print(f"✅ Tree sačuvan u: file_tree.txt")

    # ── 2. Napravi zip ────────────
    print(f"🗜️  Pakujem fajlove (.py .json .js .css .html .txt .log)...")
    broj, veličina = napravi_zip(root, ime_zipa)

    mb = veličina / (1024 * 1024)
    print(f"✅ Gotovo! {broj} fajlova • {mb:.2f} MB → {ime_zipa.name}")

    # Obriši privremeni tree fajl ako ga nije bilo pre
    # (ostaviti ga je korisno, komentarišite narednu liniju po želji)
    # tree_fajl.unlink()

if __name__ == "__main__":
    main()
