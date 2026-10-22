#!/usr/bin/env python3
"""
CLI: primijeni Moon+ replacement pravila na EPUB.

Upotreba:
  python3 tools/apply_replacements.py book.epub rules.txt --output book_fixed.epub
  python3 tools/apply_replacements.py book.epub rules.txt --dry-run

--dry-run: samo prikazi sta bi se promijenilo, ne pisi EPUB.
"""
import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.replacements import (
    load_moon_replacements, apply_to_html, summarize,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub", help="Ulazni EPUB")
    ap.add_argument("rules", help="Moon+ replacement fajl (.txt)")
    ap.add_argument("--output", "-o", help="Izlazni EPUB (default: <ulaz>_FIXED.epub)")
    ap.add_argument("--dry-run", action="store_true", help="Ne pisi EPUB")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    epub_in = Path(args.epub)
    if not epub_in.exists():
        print(f"❌ EPUB ne postoji: {epub_in}")
        return 1

    print(f"═══ 1. Ucitavam pravila ═══")
    try:
        rules = load_moon_replacements(args.rules)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    print(f"  ✅ {len(rules)} pravila")

    modes = {}
    for r in rules:
        modes[r.mode] = modes.get(r.mode, 0) + 1
    print(f"  Regex: {modes.get('regex', 0)}, Literal: {modes.get('literal', 0)}")

    print(f"\n═══ 2. Otvaram EPUB ═══")
    print(f"  {epub_in}")

    output = Path(args.output) if args.output else epub_in.with_name(
        epub_in.stem + "_FIXED.epub"
    )

    total_fires = []
    files_changed = 0
    files_total = 0

    print(f"\n═══ 3. Primjenjujem pravila ═══")
    if args.dry_run:
        print("  (DRY RUN — ne pise)")

    new_files = {}
    with zipfile.ZipFile(epub_in, "r") as zin:
        for name in zin.namelist():
            data = zin.read(name)
            if not name.lower().endswith((".xhtml", ".html", ".htm")):
                new_files[name] = data
                continue

            files_total += 1
            new_data, fires = apply_to_html(data, rules)

            if fires:
                files_changed += 1
                total_fires.extend(fires)
                if args.verbose:
                    total_count = sum(f.count for f in fires)
                    print(f"  {name}: {len(fires)} pravila, {total_count} zamjena")

            new_files[name] = new_data

    print(f"\n═══ 4. Sazetak ═══")
    print(f"  Fajlova ukupno: {files_total}")
    print(f"  Fajlova promijenjeno: {files_changed}")
    print(f"  Pravila aktivirana: {len(set((f.rule.source_line) for f in total_fires))}")
    print(f"  Ukupno zamjena: {sum(f.count for f in total_fires)}")

    if total_fires:
        print(f"\n  Top 20 pravila po broju zamjena:")
        by_rule = {}
        for f in total_fires:
            key = (f.rule.source_line, f.rule.original)
            by_rule[key] = by_rule.get(key, 0) + f.count
        for (line, orig), cnt in sorted(by_rule.items(), key=lambda x: -x[1])[:20]:
            print(f"    [{line}] {orig[:70]}  ({cnt}x)")

    if args.dry_run:
        print(f"\n  (dry run — {output} nije kreiran)")
        return 0

    print(f"\n═══ 5. Pisem novi EPUB ═══")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in new_files.items():
            zout.writestr(name, data)
    print(f"  ✅ {output}")
    print(f"     {output.stat().st_size} bajtova")

    return 0


if __name__ == "__main__":
    sys.exit(main())
