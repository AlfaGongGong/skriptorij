#!/usr/bin/env python3
"""
deploy.py — Raspakuje skriptorij ZIP iz Downloada i deployuje u projekt.

Korišćenje:
    python deploy.py                         # auto-detect ZIP iz Downloada
    python deploy.py fix_22_05_2026.zip      # konkretan ZIP (ime ili puna putanja)
    python deploy.py --dry-run               # pokaži šta bi uradilo, ne diraj fajlove

Podržava dva formata ZIPova:
    skriptorij_DD_MM_YYYY.zip  → cijeli projekt (Skriptorij/subfolder/fajl.py)
    fix_*.zip / patch_*.zip    → parcijalni fix (samo izmijenjeni fajlovi, flat ili sa strukturom)

Logika:
    - Fajlovi sa strukturom Skriptorij/... → idu u PROJECT_ROOT/...
    - Fajlovi bez strukture (flat ZIP) → idu u PROJECT_ROOT/ matchovanjem po imenu
    - Move: raspakuje u temp dir → mv u projekt (overwrite)
    - Backup: pravi _backup_TIMESTAMP/ od fajlova koje overwriteuje

Putanje (prilagodi po potrebi):
    DOWNLOAD_DIR  = /storage/emulated/0/Download
    PROJECT_ROOT  = /storage/emulated/0/termux/Skriptorij
"""

import os
import sys
import shutil
import zipfile
import tempfile
import argparse
from pathlib import Path
from datetime import datetime

# ── Konfiguracija ─────────────────────────────────────────────────────────────

DOWNLOAD_DIR  = Path("/storage/emulated/0/Download")
PROJECT_ROOT  = Path("/storage/emulated/0/termux/Skriptorij")

# Prefiks unutar ZIPa koji se strip-a (cijeli projekt ZIP)
ZIP_PROJECT_PREFIX = "Skriptorij"

# Direktorijumi koji se nikad ne diraju pri deployu
SKIP_DIRS = {"logs", "analysis/cache", "data/rod_registri", "_backup_fix_"}

# Fajlovi koji se nikad ne prepisuju (runtime state)
SKIP_FILES = {
    "dev_api.json",
    "api_state.json",
    "quota_cooldowns.json",
    "proxies.json",
}

# ZIP prefiksi koji se prepoznaju kao "projekt ZIP"
FULL_PROJECT_ZIP_PREFIXES = ("skriptorij_",)

# ZIP prefiksi koji se prepoznaju kao "fix/patch ZIP"
PATCH_ZIP_PREFIXES = ("fix_", "patch_", "hotfix_")


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "info"):
    icons = {"info": "ℹ️ ", "ok": "✅", "warn": "⚠️ ", "error": "❌", "skip": "⏭️ ", "dry": "🔍"}
    print(f"{icons.get(level, '  ')} {msg}")


def find_latest_zip(download_dir: Path) -> Path | None:
    """Nađi najnoviji skriptorij_*.zip ili fix_*.zip u Download folderu."""
    candidates = []
    for prefix in (*FULL_PROJECT_ZIP_PREFIXES, *PATCH_ZIP_PREFIXES):
        candidates.extend(download_dir.glob(f"{prefix}*.zip"))

    if not candidates:
        return None

    # Sortiraj po mtime — najnoviji prvi
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def resolve_zip(arg: str | None) -> Path:
    """Pretvori argument u Path do ZIP fajla."""
    if arg is None:
        z = find_latest_zip(DOWNLOAD_DIR)
        if z is None:
            log(f"Nema skriptorij_*.zip ni fix_*.zip u {DOWNLOAD_DIR}", "error")
            sys.exit(1)
        log(f"Auto-detected: {z.name}", "info")
        return z

    p = Path(arg)
    if p.is_absolute() and p.exists():
        return p

    # Proba u CWD pa u Download
    for search in [Path.cwd() / p.name, DOWNLOAD_DIR / p.name]:
        if search.exists():
            return search

    log(f"ZIP nije nađen: {arg}", "error")
    sys.exit(1)


def is_full_project_zip(zip_path: Path) -> bool:
    return zip_path.name.startswith(FULL_PROJECT_ZIP_PREFIXES)


def should_skip(rel_path: Path) -> bool:
    """Da li treba preskočiti ovaj fajl?"""
    if rel_path.name in SKIP_FILES:
        return True
    rel_str = str(rel_path)
    for skip_dir in SKIP_DIRS:
        if rel_str.startswith(skip_dir) or f"/{skip_dir}/" in rel_str:
            return True
    return False


def make_backup(files_to_overwrite: list[tuple[Path, Path]], backup_dir: Path, dry_run: bool):
    """Backup fajlova koji će biti overwriteani."""
    if not files_to_overwrite:
        return
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    log(f"Backup → {backup_dir.name}/", "info")
    for _, dest in files_to_overwrite:  # tuple je (ZipInfo, dest_path)
        if dest.exists():
            rel = dest.relative_to(PROJECT_ROOT)
            dst = backup_dir / rel
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, dst)
            log(f"  backup: {rel}", "dry" if dry_run else "ok")


# ── Glavna logika ─────────────────────────────────────────────────────────────

def deploy(zip_path: Path, dry_run: bool = False):
    log(f"ZIP: {zip_path}", "info")
    log(f"Projekt: {PROJECT_ROOT}", "info")
    if dry_run:
        log("DRY RUN — fajlovi se NE mijenjaju", "dry")
    print()

    if not PROJECT_ROOT.exists():
        log(f"PROJECT_ROOT ne postoji: {PROJECT_ROOT}", "error")
        sys.exit(1)

    full_zip = is_full_project_zip(zip_path)
    log(f"Tip ZIPa: {'cijeli projekt' if full_zip else 'patch/fix'}", "info")

    # Otvori ZIP i prikupi fajlove
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        log(f"Fajlova u ZIPu: {len(members)}", "info")
        print()

        deploy_plan: list[tuple[zipfile.ZipInfo, Path]] = []  # (zip_member, dest_path)
        skipped = []

        for member in members:
            arc = Path(member.filename)

            # Odredi relativnu putanju unutar projekta
            if full_zip:
                # Cijeli projekt: Skriptorij/network/rate_limiter.py → network/rate_limiter.py
                parts = arc.parts
                if len(parts) > 1 and parts[0] == ZIP_PROJECT_PREFIX:
                    rel = Path(*parts[1:])
                elif len(parts) > 1:
                    # ZIP ima drugačiji root (npr. Skriptorij_backup/...)
                    rel = Path(*parts[1:])
                else:
                    rel = arc
            else:
                # Patch ZIP: može biti flat (rate_limiter.py) ili sa strukturom
                parts = arc.parts
                if len(parts) > 1 and parts[0] == ZIP_PROJECT_PREFIX:
                    rel = Path(*parts[1:])
                elif len(parts) > 1:
                    rel = arc  # zadrži strukturu kao je
                else:
                    # Flat ZIP — matchuj po imenu fajla u projektu
                    matches = list(PROJECT_ROOT.rglob(arc.name))
                    if len(matches) == 1:
                        rel = matches[0].relative_to(PROJECT_ROOT)
                    elif len(matches) > 1:
                        # Više matcheva — uzmi prvi koji nije u backup/logs
                        good = [m for m in matches
                                if not any(s in str(m) for s in ("_backup", "logs", "cache"))]
                        if good:
                            rel = good[0].relative_to(PROJECT_ROOT)
                        else:
                            rel = matches[0].relative_to(PROJECT_ROOT)
                        log(f"Više matcheva za {arc.name} → koristim {rel}", "warn")
                    else:
                        log(f"Nema matcha za '{arc.name}' u projektu — preskačem", "skip")
                        skipped.append(str(arc))
                        continue

            # Provjeri skip listu
            if should_skip(rel):
                log(f"Zaštićen fajl, preskačem: {rel}", "skip")
                skipped.append(str(rel))
                continue

            dest = PROJECT_ROOT / rel
            deploy_plan.append((member, dest))

        # Prikaži plan
        will_overwrite = [(m, d) for m, d in deploy_plan if d.exists()]
        will_create    = [(m, d) for m, d in deploy_plan if not d.exists()]

        if will_overwrite:
            log(f"Overwrite ({len(will_overwrite)} fajlova):", "warn")
            for m, d in will_overwrite:
                log(f"  → {d.relative_to(PROJECT_ROOT)}", "warn")
        if will_create:
            log(f"Novi fajlovi ({len(will_create)}):", "ok")
            for m, d in will_create:
                log(f"  + {d.relative_to(PROJECT_ROOT)}", "ok")
        if skipped:
            log(f"Preskočeni ({len(skipped)}): {', '.join(skipped)}", "skip")

        print()

        if not deploy_plan:
            log("Nema fajlova za deploy.", "warn")
            return

        if dry_run:
            log("DRY RUN završen. Ništa nije promijenjeno.", "dry")
            return

        # Backup
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = PROJECT_ROOT / f"_backup_deploy_{ts}"
        make_backup(will_overwrite, backup_dir, dry_run=False)

        # Raspakuj u temp pa mv
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            deployed = 0
            errors = 0
            for member, dest in deploy_plan:
                try:
                    # Raspakuj u temp
                    extracted = tmp / member.filename
                    zf.extract(member, tmp)

                    # Osiguraj da destination folder postoji
                    dest.parent.mkdir(parents=True, exist_ok=True)

                    # Move (overwrite)
                    shutil.move(str(extracted), str(dest))
                    log(f"✓ {dest.relative_to(PROJECT_ROOT)}", "ok")
                    deployed += 1
                except Exception as e:
                    log(f"Greška pri deployanju {member.filename}: {e}", "error")
                    errors += 1

        print()
        log(f"Deploy završen: {deployed} fajlova deployano, {errors} grešaka", "ok" if errors == 0 else "warn")
        if will_overwrite:
            log(f"Backup starih verzija: {backup_dir.name}/", "info")

        # Premjesti ZIP iz Downloada u projekt (arhiva)
        if zip_path.parent == DOWNLOAD_DIR:
            archive_dir = PROJECT_ROOT / "_backup_deploy_zips"
            archive_dir.mkdir(exist_ok=True)
            dest_zip = archive_dir / zip_path.name
            try:
                shutil.move(str(zip_path), str(dest_zip))
                log(f"ZIP premješten u: _backup_deploy_zips/{zip_path.name}", "info")
            except Exception as e:
                log(f"ZIP premještanje neuspješno: {e}", "warn")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global PROJECT_ROOT, DOWNLOAD_DIR

    parser = argparse.ArgumentParser(
        description="Deploy Skriptorij ZIP iz Downloads u projekt (move, overwrite)."
    )
    parser.add_argument(
        "zip_file",
        nargs="?",
        default=None,
        help="Ime ili putanja ZIP fajla (opcionalno, default: najnoviji iz Downloads)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pokaži šta bi uradilo bez stvarnih izmjena"
    )
    parser.add_argument(
        "--project",
        default=None,
        help=f"Override PROJECT_ROOT (default: {PROJECT_ROOT})"
    )
    parser.add_argument(
        "--downloads",
        default=None,
        help=f"Override DOWNLOAD_DIR (default: {DOWNLOAD_DIR})"
    )
    args = parser.parse_args()

    if args.project:
        PROJECT_ROOT = Path(args.project)
    if args.downloads:
        DOWNLOAD_DIR = Path(args.downloads)

    zip_path = resolve_zip(args.zip_file)
    deploy(zip_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
