"""
epub/normalizer.py

Čisti markup koji je "preživio" iz ranijih obrada prije nego
run_epub_styler() doda svjež ornament/dropcap. Bez ovoga:
- stari, CSS-klasa-bazirani "span.dropcap" (definisan u
  _EPUB_PAPER_CSS, epub/styling.py) ostaje zalijepljen na
  pogrešnom paragrafu (često na samom naslovu poglavlja ako taj
  naslov nije bio ispravno označen kao <h1> u ranijem pokretanju
  parsera) i pravi vizuelni bug: "P" + "ROLOG" umjesto "PROLOG".
- ako se Stil tab pokrene DRUGI put na već stiliziranoj knjizi,
  novi booklyfi-dropcap/booklyfi-vijenac elementi bi se dodali
  NA VRH postojećih, umjesto da ih zamijene -> dupliranje.

normalize_chapter_html(soup) uklanja oba traga PRIJE nego
run_epub_styler pozove _add_chapter_ornament()/_add_dropcap().
"""

from bs4 import BeautifulSoup, NavigableString


def normalize_chapter_html(soup: BeautifulSoup) -> None:
    """
    Mutira soup in-place. Ne vraća ništa (isti obrazac kao
    _add_chapter_ornament / _inject_epub_global_css).
    """
    _strip_legacy_dropcap_span(soup)
    _strip_booklyfi_dropcap(soup)
    _strip_booklyfi_vijenac(soup)


def _unwrap_preserving_text(tag, replacement_text: str) -> None:
    """Zamijeni tag čistim tekstom na istom mjestu u stablu."""
    tag.replace_with(NavigableString(replacement_text))


def _strip_legacy_dropcap_span(soup: BeautifulSoup) -> None:
    """
    Uklanja STARI <span class="dropcap">X</span> (jednina, bez
    "booklyfi-" prefiksa — iz span.dropcap CSS pravila u
    _EPUB_PAPER_CSS). Slovo se vraća kao običan tekst na početak
    paragrafa.
    """
    for span in soup.find_all("span", class_="dropcap"):
        letter = span.get_text()
        _unwrap_preserving_text(span, letter)


def _strip_booklyfi_dropcap(soup: BeautifulSoup) -> None:
    """
    Uklanja dropcap koji je NAŠA verzija _add_dropcap() već
    ubacila u ranijem pokretanju Stil taba (<img class=
    "booklyfi-dropcap"> ili <span class="booklyfi-dropcap">),
    tako da se ponovno pokretanje ne duplira i _add_dropcap()
    može ispravno prepoznati paragraf iznova.
    """
    for tag in soup.find_all(["img", "span"], class_="booklyfi-dropcap"):
        if tag.name == "img":
            letter = tag.get("alt", "")
        else:
            letter = tag.get_text()
        _unwrap_preserving_text(tag, letter)


def _strip_booklyfi_vijenac(soup: BeautifulSoup) -> None:
    """
    Uklanja centralni ornament (<img>/<p class="booklyfi-
    vijenac">) koji je _add_chapter_ornament() već ubacio u
    ranijem pokretanju — potpuno se briše (nije dio teksta, ne
    treba ga vraćati kao tekst), da svjež poziv doda tačno jedan.
    """
    for tag in soup.find_all(["img", "p"], class_="booklyfi-vijenac"):
        tag.decompose()

# ═══════════════════════════════════════════════════════════════════════════
# POTPUNI STRIP — svaka knjiga izlazi identično bez obzira na ulaz
# ═══════════════════════════════════════════════════════════════════════════



def _normalize_html(soup):
    """
    Normalizuje HTML u jedinstvenu strukturu (Calibre-style).
    
    SVE knjige, bez obzira na izvor, izlaze sa:
      - <p> za tekst (ne <div>)
      - <h1>-<h3> za naslove (ne <h4>-<h6>)
      - <em>/<i>, <strong>/<b> za naglašavanje
      - <br> za prelom reda
      - Bez <font>, <center>, <table> layout
    
    Poziva se PRIJE _strip_everything.
    """
    from bs4 import NavigableString
    
    # ── 1. <div> sa tekstom → <p> ──
    for div in soup.find_all("div"):
        # Preskoči ako je strukturni wrapper (sadrži <div>/<p>/<ul>/<ol>)
        if div.find(["div", "p", "ul", "ol", "table"]):
            continue
        # Preskoči ako je prazan
        if not div.get_text(strip=True):
            continue
        # Prebaci u <p>
        div.name = "p"
        # Ukloni klase (Calibre klase)
        if div.get("class"):
            del div["class"]
    
    # ── 2. <h4>-<h6> → <h3> ──
    for h in soup.find_all(["h4", "h5", "h6"]):
        h.name = "h3"
    
    # ── 3. <font> → tekst sa <em>/<strong> ako treba ──
    for font in soup.find_all("font"):
        # Ako ima color/size, pretvori u <span style>
        style_parts = []
        if font.get("color"):
            style_parts.append(f"color:{font['color']}")
        if font.get("face"):
            style_parts.append(f"font-family:{font['face']}")
        
        if style_parts:
            span = soup.new_tag("span")
            span["style"] = ";".join(style_parts)
            font.replace_with(span)
            for child in list(font.children):
                span.append(child)
        else:
            font.unwrap()  # <font> bez stila → samo tekst
    
    # ── 4. <center> → <p style="text-align:center"> ──
    for c in soup.find_all("center"):
        p = soup.new_tag("p")
        p["style"] = "text-align:center;text-indent:0;"
        for child in list(c.children):
            p.append(child)
        c.replace_with(p)
    
    # ── 5. <table> layout → <p> ──
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        cells = table.find_all(["td", "th"])
        # Ako nije prava tabela (samo layout)
        if len(rows) <= 1 or len(cells) <= 1:
            p = soup.new_tag("p")
            p.string = table.get_text(" ", strip=True)
            table.replace_with(p)
    
    # ── 6. <span> bez stila/klase → unwrap ──
    for span in soup.find_all("span"):
        if not span.get("style") and not span.get("class") and not span.get("id"):
            span.unwrap()
    
    # ── 7. <b> → <strong>, <i> → <em> (semantički) ──
    for b in soup.find_all("b"):
        b.name = "strong"
    for i in soup.find_all("i"):
        i.name = "em"
    
    # ── 8. Deduplikacija duplih slova na početku riječi (AAutorska → Autorska) ──
    import re as _re
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name in ("script", "style"):
            continue
        original = str(text_node)
        # Nađi riječi koje počinju sa 2+ istih slova
        new_text = _re.sub(
            r'\b([A-ZŠĐČĆŽ])\1+([a-zšđčćž])',
            r'\1\2',
            original
        )
        if new_text != original:
            text_node.replace_with(new_text)
    
    # ── 8. <u>, <s>, <strike> → ukloni (bez stila) ──
    for u in soup.find_all(["u", "s", "strike", "del", "ins"]):
        u.unwrap()
    
    return soup


def _strip_everything(soup: BeautifulSoup, sacuvaj_tekst: bool = True) -> dict:
    """
    Uklanja SVE stilove, klase i nepotrebne elemente iz HTML-a — ALI:
      - Zadržava <h1>-<h6> (naslovi poglavlja — AI ili originalni)
      - Zadržava TOC elemente (<nav epub:type="toc">, <a href>, <ol>, <li>)
      - Zadržava <section> (strukturni wrapper)
      - Vraća skrivena slova u tekst (bez gubitka slova)

    Cilj: goli HTML koji se može ponovo stilizovati bez dupliranja.
    Onda stil_ai.py primjenjuje svoj jedinstveni stil.
    """
    stats = {
        "style_uklonjen": 0,
        "link_uklonjen": 0,
        "klasa_uklonjena": 0,
        "inline_style_uklonjen": 0,
        "img_uklonjen": 0,
        "span_uklonjen": 0,
        "div_uklonjen": 0,
        "skriveno_slovo_vraceno": 0,
        "toc_zadrzan": 0,
    }

    # ─── 1. Ukloni SVE <style> (i naše i tuđe) ────────────────
    for style in soup.find_all("style"):
        style.decompose()
        stats["style_uklonjen"] += 1

    # ─── 2. Ukloni SVE <link rel="stylesheet"> ────────────────
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = rel.split()
        if "stylesheet" in [r.lower() for r in rel]:
            link.decompose()
            stats["link_uklonjen"] += 1

    # ─── 3. Vrati skrivena slova iz svih <span style="font-size:1px;..."> ─
    for span in soup.find_all("span", style=True):
        s = span.get("style") or ""
        if "font-size:1px" in s or "font-size: 1px" in s or "visibility:hidden" in s:
            t = span.get_text()
            if t:
                span.replace_with(NavigableString(t))
                stats["skriveno_slovo_vraceno"] += 1
            else:
                span.decompose()

    # ─── 4. Vrati tekst iz <span class="booklyfi-dropcap"> ────
    for span in soup.find_all("span", class_="booklyfi-dropcap"):
        t = span.get_text()
        if t:
            span.replace_with(NavigableString(t))
        else:
            span.decompose()

    # ─── 5. Ukloni SVE <img> (dropcap/ornament/slike) ─────────
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        # Vrati slovo u tekst samo ako je jedan znak (dropcap)
        if alt and len(alt) <= 2:
            img.replace_with(NavigableString(alt))
            stats["skriveno_slovo_vraceno"] += 1
        else:
            img.decompose()
        stats["img_uklonjen"] += 1

    # ─── 6. Ukloni SVE <span> — tekst vrati u parent ──────────
    for span in soup.find_all("span"):
        t = span.get_text()
        if t:
            span.replace_with(NavigableString(t))
        else:
            span.decompose()
        stats["span_uklonjen"] += 1

    # ─── 7. Ukloni SVE <div> osim ako je TOC ili section wrapper ─
    for div in soup.find_all("div"):
        klase = div.get("class") or []
        if isinstance(klase, str):
            klase = klase.split()
        # ZADRŽI ako je unutar TOC-a
        parent_nav = div.find_parent("nav")
        if parent_nav and "toc" in str(parent_nav.get("epub:type", "")).lower():
            continue
        # Ako je div prazan (nema teksta unutra) — obriši
        if not div.get_text(strip=True):
            div.decompose()
            stats["div_uklonjen"] += 1
            continue
        # Ako sadrži samo blok elemente — unwrap
        sadrzi_samo_blok = all(
            (not hasattr(c, "name")) or c.name in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "br", "section", "blockquote", "ol", "ul", "li", "a", "nav")
            for c in div.children
        )
        if sadrzi_samo_blok:
            div.unwrap()
            stats["div_uklonjen"] += 1

    # ─── 8. Ukloni klase sa tagova — ALI ZADRŽI TOC tagove ────
    for tag in soup.find_all(class_=True):
        # Provjeri da li je TOC element
        parent_nav = tag.find_parent("nav")
        is_toc = parent_nav and "toc" in str(parent_nav.get("epub:type", "")).lower()
        # Provjeri da li je <a> unutar TOC-a
        if tag.name == "a" and parent_nav:
            is_toc = True
        if is_toc:
            stats["toc_zadrzan"] += 1
            continue
        klase = tag.get("class") or []
        if isinstance(klase, str):
            klase = klase.split()
        if klase:
            stats["klasa_uklonjena"] += len(klase)
            del tag["class"]

    # ─── 9. Ukloni inline stilove — ALI ZADRŽI TOC ────────────
    for tag in soup.find_all(style=True):
        parent_nav = tag.find_parent("nav")
        if parent_nav and "toc" in str(parent_nav.get("epub:type", "")).lower():
            continue
        del tag["style"]
        stats["inline_style_uklonjen"] += 1

    # ─── 10. Ukloni <body> stilove i klase ────────────────────
    body = soup.find("body")
    if body:
        for attr in ("style", "class", "bgcolor", "background", "text", "link"):
            if body.get(attr):
                del body[attr]

    return stats


