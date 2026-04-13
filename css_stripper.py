#!/usr/bin/env python3
# ============================================================================
# SKRIPTORIJ — css_stripper.py
# Prolazi kroz sve HTML/XHTML fajlove raspakovanog epuba,
# uklanja inline style="..." atribute iz tagova i pamti mapu
# klasa / id-eva → HTML tag za naknadno pariranje CSS-a.
# ============================================================================

import argparse
import json
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ── Proširenja koja se tretiraju kao HTML ─────────────────────────────────────
HTML_SUFFIXES = {".html", ".htm", ".xhtml", ".xml"}

# ── Putanja do data foldera ───────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"

# ── Uniformni ornament koji se ubacuje ispod naslova poglavlja ────────────────
SKRIPTORIJ_ORNAMENT = "─── ✦ ─── ✦ ─── ✦ ───"

# ── Uniformni CSS za sve knjige ───────────────────────────────────────────────
SKRIPTORIJ_UNIFORM_CSS = """\
/* ═══════════════════════════════════════════════════════════════
   SKRIPTORIJ — Uniformni stil za sve knjige
   Font: pisaća mašina | Tekst: crn, justified | Dropcap: crveni
   ═══════════════════════════════════════════════════════════════ */

@charset "UTF-8";

/* Osnova dokumenta */
html, body {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    font-size: 1em;
    color: #000000;
    background: #ffffff;
    margin: 0;
    padding: 0;
    text-align: justify;
}

/* ─── Oznaka "POGLAVLJE XX" ──────────────────────────────────── */
.skr-chapter-label {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    font-size: 0.85em;
    font-weight: normal;
    letter-spacing: 0.4em;
    text-transform: uppercase;
    text-align: center;
    color: #000000;
    margin: 0 0 0.8em 0;
    text-indent: 0;
    page-break-before: always;
    break-before: page;
    padding-top: 15vh;
}

/* ─── Naslov poglavlja ───────────────────────────────────────── */
h1, h2, h3,
.skr-heading {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    font-size: 1.3em;
    font-weight: bold;
    text-align: center;
    text-transform: uppercase;
    color: #000000;
    margin: 0.2em 0 0.6em;
    text-indent: 0;
    page-break-after: avoid;
    break-after: avoid;
}

/* ─── Ukras (ornament) ───────────────────────────────────────── */
.skr-ornament {
    font-family: serif;
    font-size: 1em;
    text-align: center;
    color: #333333;
    margin: 0.5em 0 3em;
    letter-spacing: 0.25em;
    text-indent: 0;
}

/* ─── Obični paragraf ────────────────────────────────────────── */
p,
.skr-body {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    font-size: 1em;
    line-height: 1.7;
    text-align: justify;
    text-indent: 1.5em;
    margin: 0;
    color: #000000;
}

/* ─── Prvi paragraf poglavlja (sa dropcapom, bez uvlake) ─────── */
p.skr-chapter-first,
.skr-chapter-first {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    font-size: 1em;
    line-height: 1.7;
    text-align: justify;
    text-indent: 0;
    margin: 1.8em 0 0;
    color: #000000;
    overflow: hidden;
}

/* ─── Dropcap ────────────────────────────────────────────────── */
.skr-dropcap {
    float: left;
    font-family: Georgia, 'Times New Roman', 'Book Antiqua', serif;
    font-size: 3.6em;
    line-height: 0.78;
    margin-right: 0.08em;
    margin-bottom: -0.05em;
    color: #cc0000;
    font-weight: bold;
}

/* ─── Naslovi koji stoje sami na stranici ────────────────────── */
.skr-title-page {
    page-break-before: always;
    break-before: page;
    page-break-after: always;
    break-after: page;
    display: block;
    text-align: center;
    padding-top: 40vh;
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def _choose_parser(path: Path) -> str:
    """Vrati odgovarajući BeautifulSoup parser za dati fajl."""
    return "xml" if path.suffix.lower() in {".xhtml", ".xml"} else "html.parser"


def strip_inline_styles(html_text: str, parser: str) -> tuple[str, dict]:
    """
    Ukloni sve style="..." atribute iz HTML/XHTML teksta.

    Vraća (izmijenjeni_html, mapa) gdje je mapa:
        {
            "tag_name": {
                "classes": ["cls1", "cls2", ...],
                "ids":     ["id1", "id2", ...]
            },
            ...
        }
    """
    soup = BeautifulSoup(html_text, parser)
    tag_map: dict[str, dict] = defaultdict(lambda: {"classes": set(), "ids": set()})
    styles_removed = 0

    for tag in soup.find_all(True):
        tag_name = tag.name or "unknown"

        # Pamti klase (html.parser vrača listu, xml parser vrača string)
        raw_class = tag.get("class", [])
        if isinstance(raw_class, str):
            raw_class = raw_class.split()
        for cls in raw_class:
            if cls:
                tag_map[tag_name]["classes"].add(cls)

        # Pamti id
        tag_id = tag.get("id", "")
        if tag_id:
            tag_map[tag_name]["ids"].add(tag_id)

        # Ukloni inline style atribut
        if tag.has_attr("style"):
            del tag["style"]
            styles_removed += 1

    # Pretvori skupove u liste radi JSON serijalizacije
    serializable_map = {
        t: {
            "classes": sorted(info["classes"]),
            "ids":     sorted(info["ids"]),
        }
        for t, info in tag_map.items()
        if info["classes"] or info["ids"]
    }

    return str(soup), serializable_map, styles_removed


def merge_maps(target: dict, source: dict) -> None:
    """Spoji source mapu u target (obje su tipa {tag: {classes, ids}})."""
    for tag, info in source.items():
        if tag not in target:
            target[tag] = {"classes": set(), "ids": set()}
        target[tag]["classes"].update(info["classes"])
        target[tag]["ids"].update(info["ids"])


def process_directory(epub_dir: Path, dry_run: bool = False,
                      inject_uniform: bool = False) -> dict:
    """
    Obradi sve HTML/XHTML fajlove u direktoriju raspakovanog epuba.

    Vraća globalnu CSS mapu i ispisuje statistike.
    Sprema css_map.json u epub_dir.
    Ako je inject_uniform=True, primjenjuje uniformni CSS stil.
    """
    html_files = sorted(
        f for f in epub_dir.rglob("*") if f.suffix.lower() in HTML_SUFFIXES
    )

    if not html_files:
        print(f"  [!] Nema HTML fajlova u: {epub_dir}")
        return {}

    global_map: dict[str, dict] = {}
    total_styles_removed = 0

    for fpath in html_files:
        try:
            original = fpath.read_text("utf-8", errors="ignore")
            parser = _choose_parser(fpath)
            new_html, file_map, n_removed = strip_inline_styles(original, parser)

            merge_maps(global_map, file_map)
            total_styles_removed += n_removed

            if not dry_run and n_removed > 0:
                fpath.write_text(new_html, encoding="utf-8")

            status = "DRY" if dry_run else ("✓" if n_removed > 0 else "—")
            print(f"  [{status}] {fpath.relative_to(epub_dir)}  "
                  f"(uklonjen style atributa: {n_removed})")
        except Exception as exc:
            print(f"  [ERR] {fpath.name}: {exc}", file=sys.stderr)

    # Pretvori skupove u sortirane liste za JSON
    serializable = {
        tag: {
            "classes": sorted(info["classes"]) if isinstance(info["classes"], set)
                       else info["classes"],
            "ids":     sorted(info["ids"]) if isinstance(info["ids"], set)
                       else info["ids"],
        }
        for tag, info in global_map.items()
    }

    if not dry_run:
        map_path = epub_dir / "css_map.json"
        map_path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n  📄 CSS mapa spremljena: {map_path}")

    print(f"\n  Ukupno uklonjen style atributa: {total_styles_removed}")
    print(f"  Tagovi s klasama/id-evima:       {len(serializable)}")

    if not dry_run and inject_uniform:
        apply_uniform_styling(epub_dir)

    return serializable


def replace_epub_css_files(epub_dir: Path) -> str | None:
    """
    Zamijeni sve CSS fajlove u epub_dir uniformnim CSS-om.

    Ako nema CSS fajlova, kreira novi na standardnoj putanji.
    Vraća relativnu putanju primarnog CSS fajla (ili None pri grešci).
    """
    css_files = sorted(epub_dir.rglob("*.css"))

    if css_files:
        for css_file in css_files:
            css_file.write_text(SKRIPTORIJ_UNIFORM_CSS, encoding="utf-8")
            print(f"  [CSS] Zamijenjen: {css_file.relative_to(epub_dir)}")
        primary_css = css_files[0]
    else:
        # Nema CSS-a — kreiraj novi
        css_dir = epub_dir / "OEBPS" / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        primary_css = css_dir / "skriptorij.css"
        primary_css.write_text(SKRIPTORIJ_UNIFORM_CSS, encoding="utf-8")
        print(f"  [CSS] Kreiran novi: {primary_css.relative_to(epub_dir)}")

    return str(primary_css.relative_to(epub_dir)).replace("\\", "/")


def ensure_css_link(html_path: Path, css_abs_path: Path) -> None:
    """
    Osiguraj da HTML fajl ima <link rel="stylesheet"> koji pokazuje
    na css_abs_path. Ako postoji stara veza, ažuriraj putanju; ako ne,
    dodaj je u <head>.
    """
    text = html_path.read_text("utf-8", errors="ignore")
    parser = _choose_parser(html_path)
    soup = BeautifulSoup(text, parser)

    css_rel = os.path.relpath(css_abs_path, html_path.parent).replace("\\", "/")

    existing = soup.find("link", attrs={"rel": "stylesheet"})
    if existing:
        existing["href"] = css_rel
        existing.attrs.pop("type", None)
        existing["type"] = "text/css"
    else:
        head = soup.find("head")
        if head:
            link = soup.new_tag("link")
            link["rel"] = "stylesheet"
            link["type"] = "text/css"
            link["href"] = css_rel
            head.append(link)

    html_path.write_text(str(soup), encoding="utf-8")


def remap_html_classes(html_text: str, parser: str) -> str:
    """
    Ukloni sve postojeće klase iz HTML tagova i dodaj uniformne klase
    prema tipu taga:
      • h1/h2/h3/h4/h5/h6 → skr-heading
      • p                  → skr-body
      • ostalo             → bez klase
    Inline style atributi se također brišu.
    """
    soup = BeautifulSoup(html_text, parser)

    for tag in soup.find_all(True):
        tag.attrs.pop("style", None)
        tag.attrs.pop("class", None)

        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            tag["class"] = ["skr-heading"]
        elif tag.name == "p":
            tag["class"] = ["skr-body"]

    return str(soup)


def apply_uniform_styling(epub_dir: Path) -> str | None:
    """
    Glavni ulaz: zamijeni CSS, remapiraj klase u HTML fajlovima i
    osiguraj da svaki HTML fajl linka uniformni CSS.

    Vraća relativnu putanju primarnog CSS fajla ili None.
    """
    print(f"\n  🎨 Primjena uniformnog stila u: {epub_dir}")

    css_rel = replace_epub_css_files(epub_dir)
    if css_rel is None:
        return None

    css_abs = epub_dir / css_rel

    html_files = sorted(
        f for f in epub_dir.rglob("*") if f.suffix.lower() in HTML_SUFFIXES
    )

    for html_path in html_files:
        try:
            text = html_path.read_text("utf-8", errors="ignore")
            parser = _choose_parser(html_path)
            new_text = remap_html_classes(text, parser)
            html_path.write_text(new_text, encoding="utf-8")
            ensure_css_link(html_path, css_abs)
            print(f"  [HTML] Uniformne klase: {html_path.relative_to(epub_dir)}")
        except Exception as exc:
            print(f"  [ERR] {html_path.name}: {exc}", file=sys.stderr)

    return css_rel


def find_epub_dirs(root: Path) -> list[Path]:
    """
    Pronađi raspakovan epub direktorij unutar root-a.

    Traži:
      1. Direktorije koji se zovu _skr_* (work_dir skriptorija)
      2. Svaki direktorij koji direktno sadrži META-INF/container.xml
    """
    candidates = []

    # _skr_* work direktoriji
    for d in root.rglob("_skr_*"):
        if d.is_dir():
            candidates.append(d)

    # Direktoriji s META-INF strukturom (standardni raspakovani epub)
    for d in root.iterdir():
        if d.is_dir() and (d / "META-INF" / "container.xml").exists():
            if d not in candidates:
                candidates.append(d)

    return sorted(candidates)


def unpack_epub(epub_path: Path) -> Path:
    """Raspakuj epub u privremeni direktorij pored njega i vrati putanju."""
    out_dir = epub_path.parent / f"_unpacked_{epub_path.stem}"
    out_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(epub_path, "r") as z:
        z.extractall(out_dir)
    print(f"  📦 Raspakovan: {epub_path.name} → {out_dir.name}")
    return out_dir


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Uklanja inline style atribute iz raspakovanog epuba i gradi CSS mapu.\n"
            "Ako nije navedena putanja, traži epub direktorije u ./data folderu."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "path",
        nargs="?",
        help=(
            "Putanja do raspakovanog epub direktorija, .epub fajla, "
            "ili direktorija koji ih sadrži. "
            "Ako nije navedeno, koristi se ./data."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Prikaži što bi bilo promijenjeno bez pisanja na disk.",
    )
    p.add_argument(
        "--output-map",
        metavar="FILE",
        help="Spremi globalnu CSS mapu u navedeni JSON fajl (uz css_map.json u epub dir-u).",
    )
    p.add_argument(
        "--inject-uniform",
        action="store_true",
        help=(
            "Primijeni uniformni CSS stil: zamijeni sve CSS fajlove uniformnim, "
            "remapiraj klase u HTML fajlovima i osiguraj CSS link u svakom fajlu."
        ),
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    dry_run: bool = args.dry_run
    inject_uniform: bool = getattr(args, "inject_uniform", False)

    # ── Odredi šta treba obraditi ─────────────────────────────────────────────
    target = Path(args.path).resolve() if args.path else DATA_DIR.resolve()

    if not target.exists():
        print(f"[GREŠKA] Putanja ne postoji: {target}", file=sys.stderr)
        return 1

    targets_to_process: list[Path] = []

    if target.is_file() and target.suffix.lower() == ".epub":
        # Jedan epub fajl — raspakuj ga
        targets_to_process.append(unpack_epub(target))

    elif target.is_dir():
        # Provjeri je li sam raspakovani epub (ima META-INF ili HTML fajlove)
        has_metainf = (target / "META-INF" / "container.xml").exists()
        has_html = any(
            f.suffix.lower() in {".html", ".xhtml"} for f in target.rglob("*")
        )

        if has_metainf or (has_html and not any(target.glob("_skr_*"))):
            targets_to_process.append(target)
        else:
            # Traži epub direktorije i .epub fajlove unutar njega
            epub_dirs = find_epub_dirs(target)
            epub_files = [
                f for f in target.rglob("*.epub")
                if "_unpacked_" not in str(f.parent)
            ]

            for d in epub_dirs:
                targets_to_process.append(d)
            for f in epub_files:
                # Raspakuj samo ako već nema raspakovan direktorij
                unpacked = f.parent / f"_unpacked_{f.stem}"
                skr_dirs = list(f.parent.glob(f"_skr_*"))
                if not unpacked.exists() and not skr_dirs:
                    targets_to_process.append(unpack_epub(f))
                elif unpacked.exists():
                    targets_to_process.append(unpacked)
                elif skr_dirs:
                    targets_to_process.extend(skr_dirs)

    if not targets_to_process:
        print("[INFO] Nema raspakovanog epuba za obradu.")
        print(f"       Tražio sam u: {target}")
        print("       Možeš navesti putanju direktno: python css_stripper.py <putanja>")
        return 0

    # ── Obradi svaki direktorij ───────────────────────────────────────────────
    combined_map: dict[str, dict] = {}

    for epub_dir in targets_to_process:
        print(f"\n{'='*60}")
        print(f"📂 Obrađujem: {epub_dir}")
        print(f"{'='*60}")
        dir_map = process_directory(epub_dir, dry_run=dry_run,
                                        inject_uniform=inject_uniform)
        merge_maps(combined_map, dir_map)

    # Serializuj combined_map (skupovi → liste)
    combined_serializable = {
        tag: {
            "classes": sorted(info["classes"]) if isinstance(info["classes"], set)
                       else info["classes"],
            "ids":     sorted(info["ids"]) if isinstance(info["ids"], set)
                       else info["ids"],
        }
        for tag, info in combined_map.items()
    }

    # ── Globalni output ───────────────────────────────────────────────────────
    if args.output_map:
        out = Path(args.output_map)
        out.write_text(
            json.dumps(combined_serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n💾 Globalna CSS mapa: {out}")

    print(f"\n✅ Gotovo. Obrađeno epub direktorija: {len(targets_to_process)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
