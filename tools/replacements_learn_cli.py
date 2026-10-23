#!/usr/bin/env python3
"""
CLI: analiza Moon+ replacement fajla — koliko glosar i anti-pattern kandidata.

Upotreba:
  python3 tools/replacements_learn_cli.py <book.epub> <rules.txt>
  python3 tools/replacements_learn_cli.py <book.epub> <rules.txt> --min-conf 0.8
  python3 tools/replacements_learn_cli.py <book.epub> <rules.txt> --json

--json: ispisi rezultat kao JSON (za dalju obradu)
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.replacements import load_moon_replacements, apply_to_html
from core.replacements_learn import (
    learn_from_fires, summarize, to_glosar_dict, to_kalkovi_list,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub", help="EPUB fajl")
    ap.add_argument("rules", help="Moon+ replacement fajl (.txt)")
    ap.add_argument("--min-conf", type=float, default=0.7,
                    help="Minimalna konfidenca za glosar (default 0.7)")
    ap.add_argument("--min-conf-kalk", type=float, default=0.85,
                    help="Minimalna konfidenca za kalkove (default 0.85)")
    ap.add_argument("--json", action="store_true", help="Ispisi kao JSON")
    ap.add_argument("--top", type=int, default=10, help="Broj top kandidata")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    epub_in = Path(args.epub)
    rules_path = Path(args.rules)

    if not epub_in.exists():
        print(f"❌ EPUB ne postoji: {epub_in}")
        return 1
    if not rules_path.exists():
        print(f"❌ Pravila ne postoje: {rules_path}")
        return 1

    # 1. Ucitaj pravila
    if not args.json:
        print(f"═══ 1. Ucitavam pravila ═══")
    rules = load_moon_replacements(str(rules_path))
    if not args.json:
        print(f"  ✅ {len(rules)} pravila")

    # 2. Primeni na EPUB
    if not args.json:
        print(f"\n═══ 2. Primenjujem na EPUB ═══")
    all_fires = []
    files_total = 0
    files_changed = 0

    with zipfile.ZipFile(epub_in) as z:
        for name in z.namelist():
            if not name.endswith((".xhtml", ".html", ".htm")):
                continue
            files_total += 1
            try:
                new_data, fires = apply_to_html(z.read(name), rules)
                if fires:
                    files_changed += 1
                    all_fires.extend(fires)
            except Exception as e:
                if args.verbose:
                    print(f"  ⚠️  {name}: {e}")

    if not args.json:
        print(f"  Fajlova: {files_total}, promenjeno: {files_changed}")
        print(f"  Ukupno fires: {len(all_fires)}")

    # 3. Analiza
    if not args.json:
        print(f"\n═══ 3. Analiza ═══")
    result = learn_from_fires(all_fires, rules)

    glosar = to_glosar_dict(result, min_confidence=args.min_conf)
    kalkovi = to_kalkovi_list(result, min_confidence=args.min_conf_kalk)

    # 4. Output
    if args.json:
        out = {
            "epub": str(epub_in),
            "rules": str(rules_path),
            "stats": {
                "total_rules": result.total_rules,
                "rules_fired": result.unique_rules_fired,
                "total_fires": result.total_fires,
                "files_total": files_total,
                "files_changed": files_changed,
            },
            "glosar": glosar,
            "kalkovi": kalkovi,
            "glosar_candidates_top": [
                {"original": c.original, "prevod": c.prevod,
                 "count": c.count, "confidence": round(c.confidence, 3),
                 "source_line": c.source_line}
                for c in result.glosar_candidates[:args.top]
            ],
            "anti_pattern_candidates_top": [
                {"pattern": c.pattern, "replacement": c.replacement,
                 "count": c.count, "confidence": round(c.confidence, 3),
                 "source_line": c.source_line}
                for c in result.anti_pattern_candidates[:args.top]
            ],
            "unused_rules": [
                {"search": u.search, "replace": u.replace, "source_line": u.source_line}
                for u in result.unused_rules
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print()
        print(summarize(result))
        print()
        print(f"═══ 4. Glosar (min_conf={args.min_conf}) — {len(glosar)} ═══")
        for k, v in list(glosar.items())[:args.top]:
            print(f"  {k:25} -> {v}")
        if len(glosar) > args.top:
            print(f"  ... i još {len(glosar) - args.top}")

        print()
        print(f"═══ 5. Kalkovi (min_conf={args.min_conf_kalk}) — {len(kalkovi)} ═══")
        for item in kalkovi[:args.top]:
            print(f"  {item['pattern'][:25]:25} -> {item['replacement'][:25]:25} "
                  f"(conf={item['confidence']:.2f})")

        if args.verbose and result.unused_rules:
            print()
            print(f"═══ 6. Neaktivna pravila ({len(result.unused_rules)}) ═══")
            for u in result.unused_rules[:args.top]:
                print(f"  [{u.source_line}] {u.search[:30]:30} -> {u.replace[:30]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
