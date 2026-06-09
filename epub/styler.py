"""epub/styler.py
===========================================================================
PREMIUM EPUB STYLER — "Stara knjižara" estetika
Booklyfi izdavački potpis

Primjenjuje konzistentni vizualni identitet na svaki EPUB koji prođe
kroz Booklyfi pipeline:

  • Hartija tekstura      — SVG pattern koji imitira staru kremasti papir
  • Header ornamenti      — SVG dekorativni dividers između poglavlja
  • Dropcap initiali      — AI-generisani SVG po prvom slovu svakog poglavlja
  • Premium tipografija   — EB Garamond / Libre Baskerville serif fontovi
  • Sadržaj (TOC)         — AI formira ako ne postoji u knjizi
  • Moon+ Reader profil   — .css fajl za direktan import u čitač

Izlaz:
  knjiga_STYLED.epub           — stilizovani EPUB
  knjiga_STYLED.css            — Moon+ Reader CSS profil

STANDALONE: radi s bilo kojim EPUB-om, ne ovisi o main pipeline-u.
===========================================================================
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)

# ── Konfiguracija stila ────────────────────────────────────────────────────────

STYLE_CONFIG = {
    # Boje — kremasta hartija stare knjige
    "paper_bg":        "#F5F0E8",   # kremasta podloga
    "paper_bg_dark":   "#EDE8DC",   # malo tamnija za alternativne stranice
    "ink_primary":     "#2C1810",   # tamno smeđa tinta
    "ink_secondary":   "#5C3A1E",   # srednje smeđa
    "ink_muted":       "#8B6914",   # zlatno-smeđa za naslove/ornamente
    "ornament_gold":   "#8B6914",   # zlatna za SVG ornamente
    "ornament_brown":  "#5C3A1E",   # smeđa za sekundarne ornamente
    "dropcap_color":   "#8B0000",   # tamno crvena za inicijale
    "dropcap_shadow":  "#5C3A1E",   # sjena inicijala
    "chapter_rule":    "#8B6914",   # zlatna linija između poglavlja

    # Tipografija
    "font_body":       "'EB Garamond', 'Libre Baskerville', 'Georgia', serif",
    "font_heading":    "'EB Garamond', 'Cinzel', 'Georgia', serif",
    "font_dropcap":    "'UnifrakturMaguntia', 'IM Fell English', serif",
    "font_size_body":  "1.05em",
    "line_height":     "1.72",
    "paragraph_indent": "1.8em",

    # Margine
    "margin_page":     "6%",
    "margin_chapter":  "2.5em",
}

# ── SVG generatori ─────────────────────────────────────────────────────────────

def _svg_paper_texture() -> str:
    """
    SVG pattern koji imitira teksturu stare kremaste hartije.
    Sadrži: fibre, mrlje, neravnine — sve inline, bez external zavisnosti.
    """
    return """<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'>
  <defs>
    <filter id='noise'>
      <feTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3'
                    stitchTiles='stitch' result='noiseOut'/>
      <feColorMatrix type='saturate' values='0' in='noiseOut' result='grey'/>
      <feBlend in='SourceGraphic' in2='grey' mode='multiply' result='blend'/>
      <feComposite in='blend' in2='SourceGraphic' operator='in'/>
    </filter>
    <filter id='grain'>
      <feTurbulence type='turbulence' baseFrequency='0.9 0.9' numOctaves='4'
                    seed='2' stitchTiles='stitch' result='turbOut'/>
      <feDisplacementMap in='SourceGraphic' in2='turbOut'
                         scale='1.5' xChannelSelector='R' yChannelSelector='G'/>
    </filter>
  </defs>
  <!-- Base kremasta boja -->
  <rect width='400' height='400' fill='#F5F0E8'/>
  <!-- Fini grain -->
  <rect width='400' height='400' fill='#E8DFC8' opacity='0.28' filter='url(#noise)'/>
  <!-- Horizontalne fibre papira -->
  <g opacity='0.06' stroke='#8B6914' stroke-width='0.3'>
    <line x1='0' y1='23'  x2='400' y2='23'/>  <line x1='0' y1='47'  x2='400' y2='47'/>
    <line x1='0' y1='71'  x2='400' y2='71'/>  <line x1='0' y1='95'  x2='400' y2='95'/>
    <line x1='0' y1='119' x2='400' y2='119'/> <line x1='0' y1='143' x2='400' y2='143'/>
    <line x1='0' y1='167' x2='400' y2='167'/> <line x1='0' y1='191' x2='400' y2='191'/>
    <line x1='0' y1='215' x2='400' y2='215'/> <line x1='0' y1='239' x2='400' y2='239'/>
    <line x1='0' y1='263' x2='400' y2='263'/> <line x1='0' y1='287' x2='400' y2='287'/>
    <line x1='0' y1='311' x2='400' y2='311'/> <line x1='0' y1='335' x2='400' y2='335'/>
    <line x1='0' y1='359' x2='400' y2='359'/> <line x1='0' y1='383' x2='400' y2='383'/>
  </g>
  <!-- Vertikalne fibre (rjeđe) -->
  <g opacity='0.03' stroke='#5C3A1E' stroke-width='0.4'>
    <line x1='80'  y1='0' x2='80'  y2='400'/>
    <line x1='160' y1='0' x2='160' y2='400'/>
    <line x1='240' y1='0' x2='240' y2='400'/>
    <line x1='320' y1='0' x2='320' y2='400'/>
  </g>
  <!-- Starosne mrlje (blage) -->
  <ellipse cx='320' cy='80'  rx='18' ry='12' fill='#C8A96E' opacity='0.08' filter='url(#grain)'/>
  <ellipse cx='60'  cy='250' rx='22' ry='8'  fill='#A08040' opacity='0.06'/>
  <ellipse cx='200' cy='350' rx='12' ry='16' fill='#B89050' opacity='0.07'/>
  <ellipse cx='350' cy='300' rx='8'  ry='20' fill='#C8A96E' opacity='0.05'/>
</svg>"""


def _svg_chapter_ornament(variant: int = 0) -> str:
    """
    SVG ornament koji se stavlja ispod naslova poglavlja.
    Više varijanti za raznolikost — rotira po poglavljima.
    """
    variants = [
        # 0 — klasični florentinski fleuron
        """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 40' width='300' height='40'>
  <g fill='none' stroke='#8B6914' stroke-width='1.2'>
    <!-- Centralna linija -->
    <line x1='0' y1='20' x2='120' y2='20'/>
    <line x1='180' y1='20' x2='300' y2='20'/>
    <!-- Centralni ornament -->
    <path d='M 130 20 Q 140 8 150 20 Q 160 32 170 20' fill='none' stroke='#8B6914' stroke-width='1.5'/>
    <circle cx='150' cy='20' r='3' fill='#8B6914' opacity='0.7'/>
    <circle cx='130' cy='20' r='2' fill='#8B6914' opacity='0.5'/>
    <circle cx='170' cy='20' r='2' fill='#8B6914' opacity='0.5'/>
    <!-- Mali ukrasi na linijama -->
    <circle cx='60'  cy='20' r='1.5' fill='#8B6914' opacity='0.4'/>
    <circle cx='240' cy='20' r='1.5' fill='#8B6914' opacity='0.4'/>
    <path d='M 55 16 L 65 24 M 55 24 L 65 16' stroke='#8B6914' stroke-width='0.8' opacity='0.3'/>
    <path d='M 235 16 L 245 24 M 235 24 L 245 16' stroke='#8B6914' stroke-width='0.8' opacity='0.3'/>
  </g>
</svg>""",
        # 1 — vijenac s listovima
        """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 40' width='300' height='40'>
  <g fill='#8B6914' opacity='0.75'>
    <line x1='0' y1='20' x2='110' y2='20' stroke='#8B6914' stroke-width='1' fill='none'/>
    <line x1='190' y1='20' x2='300' y2='20' stroke='#8B6914' stroke-width='1' fill='none'/>
    <!-- List lijevo -->
    <path d='M 115 20 Q 118 12 125 15 Q 120 20 125 25 Q 118 28 115 20 Z' opacity='0.8'/>
    <path d='M 122 20 Q 127 11 135 14 Q 129 20 135 26 Q 127 29 122 20 Z' opacity='0.7'/>
    <!-- Centralna rozeta -->
    <circle cx='150' cy='20' r='6' fill='none' stroke='#8B6914' stroke-width='1.2'/>
    <circle cx='150' cy='20' r='3' fill='#8B6914' opacity='0.6'/>
    <circle cx='150' cy='20' r='1' fill='#8B6914'/>
    <!-- List desno (zrcalo) -->
    <path d='M 185 20 Q 182 12 175 15 Q 180 20 175 25 Q 182 28 185 20 Z' opacity='0.8'/>
    <path d='M 178 20 Q 173 11 165 14 Q 171 20 165 26 Q 173 29 178 20 Z' opacity='0.7'/>
    <!-- Tačkice na linijama -->
    <circle cx='40'  cy='20' r='1.2' opacity='0.4'/>
    <circle cx='80'  cy='20' r='1.2' opacity='0.4'/>
    <circle cx='220' cy='20' r='1.2' opacity='0.4'/>
    <circle cx='260' cy='20' r='1.2' opacity='0.4'/>
  </g>
</svg>""",
        # 2 — arabeskni motiv
        """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 44' width='300' height='44'>
  <g stroke='#8B6914' fill='none'>
    <line x1='0' y1='22' x2='105' y2='22' stroke-width='0.8' opacity='0.6'/>
    <line x1='195' y1='22' x2='300' y2='22' stroke-width='0.8' opacity='0.6'/>
    <!-- Spiralni motiv lijevo -->
    <path d='M 108 22 Q 112 14 118 18 Q 122 22 118 26 Q 112 30 108 22' stroke-width='1.2' opacity='0.8'/>
    <path d='M 120 22 Q 124 13 131 17 Q 136 22 131 27 Q 124 31 120 22' stroke-width='1.1' opacity='0.7'/>
    <!-- Centralni motiv — stilizirani cvijet -->
    <circle cx='150' cy='22' r='7' stroke-width='1' opacity='0.9'/>
    <path d='M 143 22 Q 147 15 150 22 Q 153 29 150 22' stroke-width='0.9' opacity='0.6'/>
    <path d='M 150 15 Q 157 19 150 22 Q 143 25 150 22' stroke-width='0.9' opacity='0.6'/>
    <path d='M 157 22 Q 153 29 150 22 Q 147 15 150 22' stroke-width='0.9' opacity='0.6'/>
    <path d='M 150 29 Q 143 25 150 22 Q 157 19 150 22' stroke-width='0.9' opacity='0.6'/>
    <circle cx='150' cy='22' r='2.5' fill='#8B6914' opacity='0.7'/>
    <!-- Spiralni motiv desno (zrcalo) -->
    <path d='M 192 22 Q 188 14 182 18 Q 178 22 182 26 Q 188 30 192 22' stroke-width='1.2' opacity='0.8'/>
    <path d='M 180 22 Q 176 13 169 17 Q 164 22 169 27 Q 176 31 180 22' stroke-width='1.1' opacity='0.7'/>
    <!-- Točkice -->
    <circle cx='50'  cy='22' r='1.5' fill='#8B6914' opacity='0.35'/>
    <circle cx='250' cy='22' r='1.5' fill='#8B6914' opacity='0.35'/>
  </g>
</svg>""",
    ]
    return variants[variant % len(variants)]


def _svg_dropcap(letter: str, color: str = "#8B0000") -> str:
    """
    Generiše SVG inicijal (dropcap) za dato slovo.
    Bogati manuskript-stil s ornamentnim okvirom.
    Koristi se kao inline SVG direktno u HTML poglavlja.
    """
    letter = (letter or "A").upper()
    c = color
    shadow = STYLE_CONFIG["dropcap_shadow"]

    return f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 90' width='80' height='90'
     class='booklyfi-dropcap' style='float:left;margin:0 0.3em 0.1em 0;shape-outside:square()'>
  <defs>
    <linearGradient id='dcGrad_{letter}' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%'   stop-color='{c}'      stop-opacity='0.95'/>
      <stop offset='100%' stop-color='{shadow}'  stop-opacity='0.85'/>
    </linearGradient>
    <filter id='dcShadow_{letter}'>
      <feDropShadow dx='1.5' dy='1.5' stdDeviation='1.5' flood-color='{shadow}' flood-opacity='0.35'/>
    </filter>
  </defs>
  <!-- Vanjski ornamentni okvir -->
  <rect x='2' y='2' width='76' height='86' rx='4'
        fill='none' stroke='#8B6914' stroke-width='1.2' opacity='0.5'/>
  <!-- Kutni ukrasi -->
  <path d='M 2 12 Q 2 2 12 2'   fill='none' stroke='#8B6914' stroke-width='1.5' opacity='0.7'/>
  <path d='M 68 2 Q 78 2 78 12' fill='none' stroke='#8B6914' stroke-width='1.5' opacity='0.7'/>
  <path d='M 2 76 Q 2 88 12 88' fill='none' stroke='#8B6914' stroke-width='1.5' opacity='0.7'/>
  <path d='M 68 88 Q 78 88 78 76' fill='none' stroke='#8B6914' stroke-width='1.5' opacity='0.7'/>
  <!-- Kutne tačkice -->
  <circle cx='6'  cy='6'  r='1.5' fill='#8B6914' opacity='0.5'/>
  <circle cx='74' cy='6'  r='1.5' fill='#8B6914' opacity='0.5'/>
  <circle cx='6'  cy='84' r='1.5' fill='#8B6914' opacity='0.5'/>
  <circle cx='74' cy='84' r='1.5' fill='#8B6914' opacity='0.5'/>
  <!-- Slovo -->
  <text x='40' y='68'
        font-family="'IM Fell English', 'Georgia', serif"
        font-size='68'
        font-weight='bold'
        text-anchor='middle'
        fill='url(#dcGrad_{letter})'
        filter='url(#dcShadow_{letter})'
        letter-spacing='-2'>{letter}</text>
  <!-- Dekorativna linija ispod slova -->
  <line x1='15' y1='78' x2='65' y2='78' stroke='#8B6914' stroke-width='0.8' opacity='0.4'/>
</svg>"""


# ── CSS za EPUB inline styling ──────────────────────────────────────────────────

def _build_epub_css() -> str:
    """
    Generiše kompletan CSS za EPUB content dokumenti.
    Ugradit će se kao <style> blok u svaki HTML fajl i kao poseban .css fajl.
    """
    c = STYLE_CONFIG
    paper_b64 = base64.b64encode(_svg_paper_texture().encode()).decode()

    return f"""/* ═══════════════════════════════════════════════════════════
   BOOKLYFI — Premium "Stara knjižara" stilovi
   Generirano automatski — ne mijenjati ručno
   ═══════════════════════════════════════════════════════════ */

/* ── Google Fonts import (serif premium fontovi) ─────────── */
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Cinzel:wght@400;600&family=IM+Fell+English:ital@0;1&display=swap');

/* ── Hartija tekstura — podloga stranice ─────────────────── */
body, html {{
    background-color: {c['paper_bg']} !important;
    background-image: url("data:image/svg+xml;base64,{paper_b64}") !important;
    background-size: 400px 400px !important;
    background-repeat: repeat !important;
    color: {c['ink_primary']} !important;
    font-family: {c['font_body']} !important;
    font-size: {c['font_size_body']} !important;
    line-height: {c['line_height']} !important;
    margin: 0 {c['margin_page']} !important;
    text-rendering: optimizeLegibility !important;
    -webkit-font-smoothing: antialiased !important;
    hyphens: auto !important;
    orphans: 3 !important;
    widows: 3 !important;
}}

/* ── Tekst i paragrafi ───────────────────────────────────── */
p {{
    margin: 0 !important;
    padding: 0 !important;
    text-align: justify !important;
    text-indent: {c['paragraph_indent']} !important;
    font-family: {c['font_body']} !important;
    color: {c['ink_primary']} !important;
    font-feature-settings: "liga" 1, "kern" 1, "onum" 1 !important;
}}

/* Bez uvlake za prvi paragraf iza naslova i iza dropcap-a */
h1 + p, h2 + p, h3 + p,
.chapter-heading + p,
p.first-para,
p:first-of-type {{
    text-indent: 0 !important;
}}

p.has-dropcap,
p.has-dropcap::first-letter {{
    text-indent: 0 !important;
}}

/* ── Naslovi poglavlja ───────────────────────────────────── */
h1, h2 {{
    font-family: {c['font_heading']} !important;
    color: {c['ink_secondary']} !important;
    text-align: center !important;
    letter-spacing: 0.08em !important;
    font-weight: 600 !important;
    margin-top: {c['margin_chapter']} !important;
    margin-bottom: 0.3em !important;
    page-break-after: avoid !important;
    break-after: avoid !important;
}}

h1 {{
    font-size: 1.6em !important;
    border-bottom: none !important;
}}

h2 {{
    font-size: 1.25em !important;
}}

h3, h4 {{
    font-family: {c['font_heading']} !important;
    color: {c['ink_muted']} !important;
    font-size: 1.05em !important;
    font-style: italic !important;
    text-align: center !important;
    margin-top: 1.5em !important;
    margin-bottom: 0.4em !important;
}}

/* ── Ornament ispod naslova poglavlja ────────────────────── */
.chapter-ornament {{
    display: block !important;
    text-align: center !important;
    margin: 0.4em auto 1.8em auto !important;
    opacity: 0.85 !important;
}}

/* ── Dropcap SVG inicijal ────────────────────────────────── */
.booklyfi-dropcap {{
    float: left !important;
    margin: 0 0.25em 0 0 !important;
    line-height: 1 !important;
    shape-outside: square() !important;
}}

.dropcap-wrap {{
    display: block !important;
    overflow: hidden !important;
}}

/* ── Citati ──────────────────────────────────────────────── */
blockquote {{
    margin: 1.5em 2em !important;
    padding: 0.5em 1em !important;
    border-left: 3px solid {c['ornament_gold']} !important;
    color: {c['ink_secondary']} !important;
    font-style: italic !important;
    background: rgba(139, 105, 20, 0.05) !important;
}}

/* ── Naglašeni tekst ─────────────────────────────────────── */
em, i {{
    font-style: italic !important;
    color: {c['ink_secondary']} !important;
}}

strong, b {{
    font-weight: 700 !important;
    color: {c['ink_primary']} !important;
}}

/* ── Horizontalne linije ─────────────────────────────────── */
hr {{
    border: none !important;
    border-top: 1px solid {c['chapter_rule']} !important;
    margin: 2em auto !important;
    width: 60% !important;
    opacity: 0.5 !important;
}}

/* ── Linkovi u TOC-u ─────────────────────────────────────── */
a {{
    color: {c['ink_secondary']} !important;
    text-decoration: none !important;
}}

a:hover {{
    text-decoration: underline !important;
    color: {c['ink_primary']} !important;
}}

/* ── Sadržaj (TOC) ───────────────────────────────────────── */
nav#toc, .toc-page, .table-of-contents {{
    background: rgba(139, 105, 20, 0.04) !important;
    padding: 1.5em !important;
    border: 1px solid rgba(139, 105, 20, 0.2) !important;
    border-radius: 4px !important;
}}

nav#toc ol, nav#toc ul,
.toc-page ol, .toc-page ul {{
    list-style: none !important;
    padding: 0 !important;
    margin: 0 !important;
}}

nav#toc li, .toc-page li {{
    padding: 0.3em 0 !important;
    border-bottom: 1px dotted rgba(139, 105, 20, 0.25) !important;
    font-family: {c['font_heading']} !important;
    font-size: 0.95em !important;
}}

/* ── Straničenje ─────────────────────────────────────────── */
@page {{
    margin: 1.5cm 2cm !important;
}}

/* ── Print poboljšanja ───────────────────────────────────── */
@media print {{
    body {{ background-image: none !important; background-color: white !important; }}
    .booklyfi-dropcap {{ print-color-adjust: exact !important; }}
}}

/* ── Moon+ Reader specifični overrides ───────────────────── */
/* (Moon+ čita inline CSS, ignorira neke background-image) */
.moon-reader body {{
    background-color: {c['paper_bg']} !important;
}}
"""


# ── Moon+ Reader CSS profil ─────────────────────────────────────────────────────

def _build_moonreader_css() -> str:
    """
    CSS profil specifično optimiziran za Moon+ Reader.
    Snima se kao zasebni .css fajl koji korisnik importuje u čitač.
    """
    c = STYLE_CONFIG
    return f"""/* ═══════════════════════════════════════════════════════════
   BOOKLYFI — Moon+ Reader profil
   "Stara knjižara" estetika
   Import: Moon+ Reader → Postavke → Stil teksta → Vlastiti CSS
   ═══════════════════════════════════════════════════════════ */

body {{
    background-color: {c['paper_bg']} !important;
    color: {c['ink_primary']} !important;
    font-family: 'Georgia', serif !important;
    font-size: 100% !important;
    line-height: 1.7 !important;
    text-align: justify !important;
    margin: 0 3% !important;
}}

p {{
    text-indent: 1.5em !important;
    margin: 0 !important;
    orphans: 3 !important;
    widows: 3 !important;
}}

h1, h2, h3 {{
    color: {c['ink_secondary']} !important;
    text-align: center !important;
    font-family: 'Georgia', serif !important;
    letter-spacing: 0.06em !important;
    margin-top: 2em !important;
    margin-bottom: 0.5em !important;
}}

h1 {{ font-size: 1.5em !important; }}
h2 {{ font-size: 1.2em !important; }}

blockquote {{
    margin: 1.2em 1.5em !important;
    padding-left: 0.8em !important;
    border-left: 2px solid {c['ornament_gold']} !important;
    color: {c['ink_secondary']} !important;
    font-style: italic !important;
}}

.chapter-ornament svg {{
    display: block !important;
    margin: 0 auto !important;
}}

a {{ color: {c['ink_secondary']} !important; text-decoration: none !important; }}
em {{ font-style: italic !important; color: {c['ink_secondary']} !important; }}
strong {{ font-weight: bold !important; }}

/* Dropcap fallback (Moon+ možda ne prikaže SVG) */
p.has-dropcap::first-letter {{
    float: left !important;
    font-size: 3.2em !important;
    line-height: 0.85 !important;
    margin: 0.05em 0.1em 0 0 !important;
    color: {c['dropcap_color']} !important;
    font-family: 'Georgia', serif !important;
    font-weight: bold !important;
}}
"""


# ── EPUB obrada ─────────────────────────────────────────────────────────────────

def _read_epub(epub_path: Path) -> dict[str, bytes]:
    """Čita sve fajlove iz EPUB-a kao {path: bytes}."""
    files = {}
    with zipfile.ZipFile(epub_path, "r") as z:
        for name in z.namelist():
            files[name] = z.read(name)
    return files


def _write_epub(epub_path: Path, files: dict[str, bytes]) -> None:
    """Piše EPUB fajl iz rječnika {path: bytes}."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".epub.tmp", dir=epub_path.parent)
    try:
        # mimetype mora biti prvi, nestisnuti
        with zipfile.ZipFile(tmp_path, "w") as z:
            if "mimetype" in files:
                z.writestr(
                    zipfile.ZipInfo("mimetype"),
                    files["mimetype"],
                    compress_type=zipfile.ZIP_STORED,
                )
        with zipfile.ZipFile(tmp_path, "a", zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items():
                if name == "mimetype":
                    continue
                z.writestr(name, data)
        os.close(tmp_fd)
        shutil.move(tmp_path, str(epub_path))
    except Exception:
        try:
            os.close(tmp_fd)
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def _get_html_files(files: dict[str, bytes]) -> list[str]:
    """Vraća listu putanja HTML/XHTML content fajlova."""
    return [
        n for n in files
        if n.lower().endswith((".html", ".xhtml", ".htm"))
        and "toc" not in n.lower().replace("-", "").replace("_", "")[:10]
    ]


def _is_chapter_html(name: str, html: str) -> bool:
    """Da li je ovo content fajl (ne metadata, ne TOC, ne cover)."""
    lower = name.lower()
    if any(x in lower for x in ("cover", "titlepage", "copyright", "colophon")):
        return False
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(strip=True)
    return len(text) > 200


def _inject_css_into_html(html: str, css: str) -> str:
    """Ubacuje <style> blok u <head> HTML dokumenta."""
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("head")
    if not head:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    # Ukloni stare booklyfi stilove ako postoje
    for old in soup.find_all("style", attrs={"data-booklyfi": True}):
        old.decompose()

    style_tag = soup.new_tag("style", type="text/css")
    style_tag["data-booklyfi"] = "1"
    style_tag.string = css
    head.append(style_tag)

    # Dodaj Google Fonts link za EPUB online renderere
    existing_links = [l.get("href", "") for l in soup.find_all("link", rel="stylesheet")]
    if not any("googleapis" in l for l in existing_links):
        gf_link = soup.new_tag("link", rel="stylesheet")
        gf_link["href"] = (
            "https://fonts.googleapis.com/css2?"
            "family=EB+Garamond:ital,wght@0,400;0,500;1,400"
            "&family=IM+Fell+English:ital@0;1"
            "&display=swap"
        )
        head.append(gf_link)

    return str(soup)


def _add_chapter_ornament(soup: BeautifulSoup, ornament_idx: int) -> None:
    """Dodaje SVG ornament ispod prvog h1/h2 u dokumentu."""
    heading = soup.find(["h1", "h2"])
    if not heading:
        return

    orn_svg = _svg_chapter_ornament(ornament_idx)
    orn_tag = BeautifulSoup(
        f'<div class="chapter-ornament">{orn_svg}</div>', "html.parser"
    ).find("div")

    if orn_tag:
        heading.insert_after(orn_tag)


def _add_dropcap(soup: BeautifulSoup) -> bool:
    """
    Dodaje SVG dropcap na prvi paragraf poglavlja.
    Vraća True ako je dropcap dodan.
    """
    # Nađi prvi "pravi" paragraf (dovoljno teksta, nije samo whitespace)
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) < 20:
            continue

        # Izvuci prvo slovo
        first_char = None
        for content in p.contents:
            if isinstance(content, NavigableString):
                stripped = content.strip()
                if stripped:
                    first_char = stripped[0].upper()
                    rest_of_first_node = stripped[1:]
                    break
            elif hasattr(content, "get_text"):
                t = content.get_text(strip=True)
                if t:
                    first_char = t[0].upper()
                    break

        if not first_char or not first_char.isalpha():
            continue

        # Generiši SVG dropcap
        dropcap_svg = _svg_dropcap(first_char, STYLE_CONFIG["dropcap_color"])

        # Rekonstruiši paragraf s dropcap-om
        p["class"] = p.get("class", []) + ["has-dropcap"]

        new_p_html = f'<p class="has-dropcap dropcap-wrap">{dropcap_svg}'

        # Dodaj ostatak teksta
        for i, content in enumerate(list(p.contents)):
            if isinstance(content, NavigableString):
                txt = str(content)
                if i == 0 and txt.strip():
                    new_p_html += txt[1:]  # preskoči prvo slovo
                else:
                    new_p_html += txt
            else:
                new_p_html += str(content)

        new_p_html += "</p>"

        new_p = BeautifulSoup(new_p_html, "html.parser").find("p")
        if new_p:
            p.replace_with(new_p)
        return True

    return False


# ── TOC generacija ─────────────────────────────────────────────────────────────

def _extract_chapters_from_epub(files: dict[str, bytes]) -> list[dict]:
    """
    Izvlači listu poglavlja iz EPUB-a: {title, href, order}.
    Čita OPF spine za redosljed, naslove iz HTML headinga.
    """
    chapters = []

    # Nađi OPF fajl
    opf_content = None
    opf_path = ""
    container_xml = files.get("META-INF/container.xml", b"")
    if container_xml:
        m = re.search(rb'full-path="([^"]+\.opf)"', container_xml)
        if m:
            opf_path = m.group(1).decode("utf-8", errors="replace")
            opf_content = files.get(opf_path, b"")

    if not opf_content:
        for name, data in files.items():
            if name.endswith(".opf"):
                opf_content = data
                opf_path = name
                break

    if not opf_content:
        return chapters

    try:
        opf_soup = BeautifulSoup(opf_content, "xml")
    except Exception:
        opf_soup = BeautifulSoup(opf_content, "lxml")

    # Čitaj spine redosljed
    spine = opf_soup.find("spine")
    manifest = opf_soup.find("manifest")
    if not spine or not manifest:
        return chapters

    id_to_href = {}
    for item in manifest.find_all("item"):
        item_id = item.get("id", "")
        href = item.get("href", "")
        if href.lower().endswith((".html", ".xhtml", ".htm")):
            id_to_href[item_id] = href

    opf_dir = str(Path(opf_path).parent)

    order = 0
    for itemref in spine.find_all("itemref"):
        idref = itemref.get("idref", "")
        href = id_to_href.get(idref, "")
        if not href:
            continue

        # Resolvi punu putanju unutar EPUB-a
        if opf_dir and opf_dir != ".":
            full_path = f"{opf_dir}/{href}"
        else:
            full_path = href

        html_bytes = files.get(full_path, files.get(href, b""))
        if not html_bytes:
            continue

        html_str = html_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_str, "html.parser")

        # Izvuci naslov
        title = ""
        for tag in ["h1", "h2", "h3", "title"]:
            t = soup.find(tag)
            if t and t.get_text(strip=True):
                title = t.get_text(strip=True)
                break

        text = soup.get_text(strip=True)
        if len(text) < 50:
            continue  # preskoči prazne fajlove

        order += 1
        chapters.append({
            "title": title or f"Poglavlje {order}",
            "href": href,
            "full_path": full_path,
            "order": order,
        })

    return chapters


def _toc_exists_in_epub(files: dict[str, bytes]) -> bool:
    """Provjerava da li EPUB već ima funkcionalni TOC s poglavijima."""
    for name, data in files.items():
        lower = name.lower()
        if "toc" in lower or "contents" in lower or "sadrzaj" in lower:
            try:
                text = data.decode("utf-8", errors="replace")
                soup = BeautifulSoup(text, "html.parser")
                links = soup.find_all("a", href=True)
                if len(links) >= 3:
                    return True
            except Exception:
                pass
    return False


def _build_toc_html(chapters: list[dict], book_title: str = "") -> str:
    """Generiše HTML TOC stranicu."""
    c = STYLE_CONFIG
    paper_b64 = base64.b64encode(_svg_paper_texture().encode()).decode()

    items = ""
    for ch in chapters:
        title = ch["title"].strip()
        href = ch["href"]
        order = ch["order"]
        items += (
            f'<li class="toc-item">'
            f'<span class="toc-num">{order}</span>'
            f'<a href="{href}" class="toc-link">{title}</a>'
            f'<span class="toc-dots"></span>'
            f'</li>\n'
        )

    return f"""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="bs">
<head>
<meta charset="utf-8"/>
<title>Sadržaj</title>
<style>
body {{
    background-color: {c['paper_bg']};
    background-image: url("data:image/svg+xml;base64,{paper_b64}");
    background-size: 400px 400px;
    color: {c['ink_primary']};
    font-family: {c['font_body']};
    margin: 0 8%;
    padding: 2em 0;
}}
.toc-title {{
    font-family: {c['font_heading']};
    font-size: 1.8em;
    color: {c['ink_secondary']};
    text-align: center;
    letter-spacing: 0.1em;
    margin-bottom: 0.3em;
}}
.toc-book-title {{
    font-family: {c['font_heading']};
    font-size: 1.1em;
    color: {c['ink_muted']};
    text-align: center;
    font-style: italic;
    margin-bottom: 1.5em;
}}
.toc-ornament {{ text-align: center; margin: 0.5em 0 2em 0; }}
.toc-list {{
    list-style: none;
    padding: 0;
    margin: 0;
}}
.toc-item {{
    display: flex;
    align-items: baseline;
    padding: 0.4em 0;
    border-bottom: 1px dotted rgba(139,105,20,0.3);
    gap: 0.5em;
}}
.toc-num {{
    font-family: {c['font_heading']};
    font-size: 0.75em;
    color: {c['ornament_gold']};
    min-width: 1.8em;
    font-style: italic;
}}
.toc-link {{
    color: {c['ink_primary']};
    text-decoration: none;
    font-family: {c['font_heading']};
    font-size: 0.95em;
    flex: 1;
}}
.toc-link:hover {{ color: {c['ink_secondary']}; text-decoration: underline; }}
</style>
</head>
<body>
<p class="toc-title">Sadržaj</p>
{"<p class='toc-book-title'>" + book_title + "</p>" if book_title else ""}
<div class="toc-ornament">{_svg_chapter_ornament(1)}</div>
<ol class="toc-list">
{items}
</ol>
</body>
</html>"""


def _ai_generate_toc_titles(
    chapters: list[dict],
    fleet,
    log_callback=None,
) -> list[dict]:
    """
    Ako poglavlja nemaju naslove (samo 'Poglavlje N'),
    traži AI da ih imenuje na osnovu sadržaja.
    """
    unnamed = [ch for ch in chapters if ch["title"].startswith("Poglavlje ")]
    if not unnamed or fleet is None:
        return chapters

    def _log(msg):
        if log_callback:
            log_callback(msg, "tech")
        logger.info("[styler/toc] %s", msg)

    _log(f"AI generira {len(unnamed)} naslova poglavlja...")

    # Skupi uzorke teksta
    samples_txt = ""
    for ch in unnamed[:12]:
        sample = ch.get("_text_sample", "")[:300]
        if sample:
            samples_txt += f"\nPoglavlje {ch['order']}:\n{sample}\n"

    if not samples_txt:
        return chapters

    prompt = f"""Na osnovu ovih odlomaka iz knjige, predloži kratke naslove poglavlja na bosanskom/hrvatskom.

{samples_txt}

Vrati ISKLJUČIVO JSON:
{{"naslovi": [{{"order": 1, "naslov": "..."}}]}}"""

    try:
        import asyncio
        from network.provider_router import call_provider

        async def _call():
            return await call_provider(
                prompt=prompt,
                uloga="ANALIZA",
                fleet=fleet,
                max_tokens=800,
                temperature=0.3,
            )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_call())
        finally:
            loop.close()

        if result:
            clean = re.sub(r"```(?:json)?\s*", "", result).replace("```", "").strip()
            data = json.loads(clean)
            order_to_title = {
                item["order"]: item["naslov"]
                for item in data.get("naslovi", [])
            }
            for ch in chapters:
                if ch["order"] in order_to_title:
                    ch["title"] = order_to_title[ch["order"]]
    except Exception as e:
        _log(f"AI TOC generacija pala: {e}")

    return chapters


# ── Glavna funkcija ─────────────────────────────────────────────────────────────

def run_epub_styler(
    epub_path: str | Path,
    fleet=None,
    output_path: str | Path | None = None,
    log_callback=None,
    options: dict | None = None,
) -> dict:
    """
    Primjenjuje premium "Stara knjižara" stil na EPUB.

    Parametri:
        epub_path    — ulazni EPUB fajl
        fleet        — FleetManager (za AI TOC generaciju)
        output_path  — izlazni EPUB (None = dodaje _STYLED suffix)
        log_callback — f(msg, atype) za log
        options      — override opcije:
            add_dropcaps: bool (default True)
            add_ornaments: bool (default True)
            add_toc: bool (default True)
            ai_toc_titles: bool (default True)

    Vraća:
        {"ok": bool, "epub_path": str, "moonreader_css": str,
         "chapters": int, "dropcaps_added": int, "toc_created": bool, "error": str|None}
    """
    epub_path = Path(epub_path)
    opts = {
        "add_dropcaps":    True,
        "add_ornaments":   True,
        "add_toc":         True,
        "ai_toc_titles":   True,
    }
    if options:
        opts.update(options)

    def _log(msg: str, atype: str = "info"):
        logger.info("[styler] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    result = {
        "ok": False,
        "epub_path": "",
        "moonreader_css": "",
        "chapters": 0,
        "dropcaps_added": 0,
        "toc_created": False,
        "error": None,
    }

    if not epub_path.exists():
        result["error"] = f"EPUB nije pronađen: {epub_path}"
        _log(f"❌ {result['error']}", "error")
        return result

    _log(f"📖 Stilizacija: {epub_path.name}", "system")

    # Odabir izlazne putanje
    if output_path:
        out_path = Path(output_path)
    else:
        stem = epub_path.stem
        out_path = epub_path.parent / f"{stem}_STYLED.epub"

    # Kopiraj original
    shutil.copy2(str(epub_path), str(out_path))

    try:
        files = _read_epub(out_path)
    except Exception as e:
        result["error"] = f"Greška pri čitanju EPUB: {e}"
        _log(f"❌ {result['error']}", "error")
        return result

    _log(f"   → {len(files)} fajlova u EPUB-u", "tech")

    # ── Generiši CSS ─────────────────────────────────────────────────────────
    epub_css = _build_epub_css()
    mr_css   = _build_moonreader_css()

    # ── Izvuci poglavlja ──────────────────────────────────────────────────────
    _log("📚 Analiza strukture knjige...", "tech")
    chapters = _extract_chapters_from_epub(files)
    result["chapters"] = len(chapters)
    _log(f"   → {len(chapters)} poglavlja pronađeno", "tech")

    # ── Provjeri/kreiraj TOC ──────────────────────────────────────────────────
    toc_created = False
    if opts["add_toc"] and not _toc_exists_in_epub(files) and chapters:
        _log("📋 TOC ne postoji — kreiram...", "system")

        # Skupi uzorke teksta za AI imenovanje
        for ch in chapters:
            html_b = files.get(ch["full_path"], files.get(ch["href"], b""))
            if html_b:
                soup_tmp = BeautifulSoup(
                    html_b.decode("utf-8", errors="replace"), "html.parser"
                )
                ch["_text_sample"] = soup_tmp.get_text(separator=" ", strip=True)[:400]

        if opts["ai_toc_titles"] and fleet:
            _log("🤖 AI imenuje poglavlja...", "system")
            chapters = _ai_generate_toc_titles(chapters, fleet, log_callback)

        # Generiši TOC HTML
        book_title = ""
        opf_bytes = b""
        for name, data in files.items():
            if name.endswith(".opf"):
                opf_bytes = data
                break
        if opf_bytes:
            opf_soup = BeautifulSoup(opf_bytes, "xml")
            t = opf_soup.find("dc:title")
            if t:
                book_title = t.get_text(strip=True)

        toc_html = _build_toc_html(chapters, book_title)

        # Nađi gdje da smjestimo TOC u EPUB-u
        # Pokušaj naći OPF direktorij
        opf_dir = ""
        container = files.get("META-INF/container.xml", b"")
        if container:
            m = re.search(rb'full-path="([^"]+\.opf)"', container)
            if m:
                opf_dir = str(Path(m.group(1).decode()).parent)
                if opf_dir == ".":
                    opf_dir = ""

        toc_fname = f"{opf_dir}/booklyfi_toc.xhtml" if opf_dir else "booklyfi_toc.xhtml"
        toc_fname = toc_fname.lstrip("/")
        files[toc_fname] = toc_html.encode("utf-8")

        # Dodaj u OPF manifest i spine (na početku)
        for opf_name in list(files.keys()):
            if opf_name.endswith(".opf"):
                opf_str = files[opf_name].decode("utf-8", errors="replace")
                toc_href = Path(toc_fname).name if opf_dir else toc_fname

                if "booklyfi_toc" not in opf_str:
                    opf_str = opf_str.replace(
                        "</manifest>",
                        f'  <item id="booklyfi-toc" href="{toc_href}" '
                        f'media-type="application/xhtml+xml"/>\n  </manifest>',
                    )
                    opf_str = opf_str.replace(
                        "<spine",
                        '<spine>\n    <itemref idref="booklyfi-toc"/>\n    <spine_placeholder',
                    ).replace(
                        '<spine_placeholder',
                        "",
                    )
                files[opf_name] = opf_str.encode("utf-8")
                break

        toc_created = True
        result["toc_created"] = True
        _log(f"✅ TOC kreiran ({len(chapters)} stavki)", "success")

    # ── Primijeni stilove na HTML fajlove ─────────────────────────────────────
    _log("🎨 Primjenjujem premium stilove...", "system")

    dropcaps_added = 0
    ornament_idx = 0
    modified_count = 0

    html_names = _get_html_files(files)

    for fname in html_names:
        html_bytes = files[fname]
        html_str = html_bytes.decode("utf-8", errors="replace")

        if not _is_chapter_html(fname, html_str):
            continue

        soup = BeautifulSoup(html_str, "html.parser")

        # Ornament ispod naslova poglavlja
        if opts["add_ornaments"]:
            _add_chapter_ornament(soup, ornament_idx)
            ornament_idx += 1

        # Dropcap na prvom paragrafu
        if opts["add_dropcaps"]:
            if _add_dropcap(soup):
                dropcaps_added += 1

        # CSS inject
        new_html = _inject_css_into_html(str(soup), epub_css)
        files[fname] = new_html.encode("utf-8")
        modified_count += 1

    _log(f"   → {modified_count} fajlova stilizovano", "tech")
    _log(f"   → {dropcaps_added} dropcap inicijala dodano", "tech")

    result["dropcaps_added"] = dropcaps_added

    # ── Snimaj EPUB ───────────────────────────────────────────────────────────
    _log("💾 Snimam stilizovani EPUB...", "tech")
    try:
        _write_epub(out_path, files)
    except Exception as e:
        result["error"] = f"Greška pri snimanju EPUB: {e}"
        _log(f"❌ {result['error']}", "error")
        return result

    # ── Moon+ Reader CSS profil ───────────────────────────────────────────────
    mr_css_path = out_path.with_suffix(".css")
    mr_css_path.write_text(mr_css, encoding="utf-8")
    _log(f"📱 Moon+ Reader profil: {mr_css_path.name}", "success")

    result.update({
        "ok": True,
        "epub_path": str(out_path),
        "moonreader_css": str(mr_css_path),
        "toc_created": toc_created,
    })

    _log(
        f"🎉 Stilizacija završena: {out_path.name} "
        f"({dropcaps_added} dropcap, {len(chapters)} pogl.)",
        "success",
    )
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Upotreba: python -m epub.styler <knjiga.epub> [izlaz_STYLED.epub]")
        sys.exit(1)

    def _cli_log(msg, atype="info"):
        icons = {"system": "🔷", "success": "✅", "error": "❌",
                 "warning": "⚠️", "tech": "  ·", "info": "ℹ️"}
        print(f"{icons.get(atype, '')} {msg}")

    res = run_epub_styler(
        sys.argv[1],
        output_path=sys.argv[2] if len(sys.argv) > 2 else None,
        log_callback=_cli_log,
    )

    if res["ok"]:
        print(f"\n✅ Gotovo!")
        print(f"   EPUB:        {res['epub_path']}")
        print(f"   Moon+ CSS:   {res['moonreader_css']}")
        print(f"   Poglavlja:   {res['chapters']}")
        print(f"   Dropcaps:    {res['dropcaps_added']}")
        print(f"   TOC kreiran: {res['toc_created']}")
    else:
        print(f"\n❌ Greška: {res['error']}")
        sys.exit(1)
