"""epub/styler.py — BOOKLYFI STYLER v2 (konačna verzija)
===========================================================================
JEDINSTVENI FORMAT ZA SVE KNJIGE.

PRAVILA:
  1. Obriši SVE staro (css, klase, dropcap, ornament, sadržaj, toc, ncx)
  2. Normalizuj HTML (div→p, h4-h6→h3, font→unwrap, deduplikacija AA→A)
  3. Detektuj STVARNA poglavlja (isključi uvod/o autoru/impresum/sadržaj)
  4. Za svako poglavlje: vijenac → POGLAVLJE N → dropcap
  5. Dropcap: 4em, pokriva 3+ reda, prvo slovo nevidljivo ali u tekstu
  6. Novi toc.ncx i toc.xhtml — SAMO stvarna poglavlja
  7. Svi TOC-ovi i ncx-ovi iz EPUB-a se brišu, pravi se jedan
===========================================================================
"""

from __future__ import annotations

import base64
import copy
import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

_PNG_CACHE: dict[str, str] = {}


logger = logging.getLogger(__name__)


STYLED_OUTPUT_DIR = "/storage/emulated/0/Books/MoonReader/STYLED"


ORNAMENTS_DIR = "/storage/emulated/0/Books/MoonReader/ornaments_small_size"


CENTER_ORNAMENT_PNG = "center_ornament.png"


def _png_b64(fname: str) -> str:
    if fname in _PNG_CACHE:
        return _PNG_CACHE[fname]
    path = os.path.join(ORNAMENTS_DIR, fname)
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            _PNG_CACHE[fname] = b64
            return b64
    return ""


def _scan_dropcaps() -> dict[str, str]:
    m = {}
    if not os.path.isdir(ORNAMENTS_DIR):
        return m
    for fname in sorted(os.listdir(ORNAMENTS_DIR)):
        if not fname.lower().endswith(".png"):
            continue
        stem = fname[:-4]
        if len(stem) in (1, 2) and stem.isalpha():
            m.setdefault(stem.upper(), fname)
    return m


DROPCAP_MAP = _scan_dropcaps()


CSS = """
body { background:#FDF6E3; color:#3E2723; font-family:Georgia,serif;
       font-size:1em; line-height:1.6; margin:0 5%; padding:0; }
p { margin:0; padding:0; text-indent:1.8em; font-size:1em; line-height:1.6; }
p.booklyfi-prvi { text-indent:0; margin-top:0.5em; margin-bottom:0.3em; }
p.booklyfi-dijalog { margin:0.3em 0; padding-left:1.5em; text-indent:-1em; }
h1.booklyfi-naslov { color:#5D4037; text-align:center;
    font-size:1.8em; font-weight:600; letter-spacing:0.05em;
    margin:0.5em 0 0.8em 0; line-height:1.3; text-indent:0; }
img.booklyfi-vijenac { display:block; width:70%; height:auto;
    margin:0.5em auto 0.8em auto; }
img.booklyfi-dropcap { float:left; display:block;
    width:4em; height:auto; max-width:none;
    margin:0.1em 0.15em 0 0; padding:0; vertical-align:top; }
em, i { font-style:italic; }
strong, b { font-weight:700; }
"""


def _ukloni_sve(soup: BeautifulSoup) -> None:
    # Style/link
    for style in soup.find_all("style"):
        style.decompose()
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        if "stylesheet" in [r.lower() for r in rel]:
            link.decompose()

    # Ornamenti
    for tag in soup.find_all("img", class_="booklyfi-vijenac"):
        tag.decompose()
    for tag in soup.find_all("img", class_="booklyfi-ornament"):
        tag.decompose()
    for tag in soup.find_all("div", class_="booklyfi-ornament"):
        tag.decompose()
    for tag in soup.find_all("p", class_="booklyfi-vijenac"):
        tag.decompose()

    # Dropcapi
    for tag in soup.find_all("img", class_="booklyfi-dropcap"):
        tag.decompose()
    for tag in soup.find_all("span", class_="booklyfi-dropcap"):
        tag.decompose()
    from bs4 import NavigableString as _NS

    for tag in soup.find_all("span", class_="booklyfi-crtica"):
        _sljedeci = tag.next_sibling
        _prvo = _sljedeci.lstrip()[:1] if isinstance(_sljedeci, _NS) else ""
        if _prvo and _prvo in "\"\u201e\u201c\u201d\u00ab'":
            tag.decompose()  # umjetna crtica ispred navodnika
        else:
            tag.replace_with(_NS(tag.get_text()))  # prava crtica replike

    # Skrivena slova — VRATI SLOVO U TEKST
    for span in soup.find_all("span", style=True):
        s = span.get("style") or ""
        if "font-size:1px" in s or "font-size: 1px" in s or "font-size:0" in s:
            slovo = span.get_text(strip=True)
            span.replace_with(slovo)

    # Klase booklyfi-*
    for el in soup.find_all(class_=True):
        classes = el.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        new_c = [c for c in classes if not c.startswith("booklyfi-")]
        if new_c:
            el["class"] = new_c
        elif el.get("class") is not None:
            del el["class"]

    # F0.40: Obrisi SVE ostale klase i inline stilove na SVIM tagovima (osim slika)
    for tag in soup.find_all(True):
        if tag.name not in ("img", "image"):
            # Style
            if "style" in tag.attrs:
                style_val = tag["style"]
                if "font-size:1px" not in style_val and "booklyfi-dropcap" not in tag.get("class", []):
                    del tag["style"]
            # Class
            if "class" in tag.attrs:
                cls = tag["class"]
                if not any(c.startswith("booklyfi-") for c in cls) and "booklyfi-dropcap" not in cls:
                    del tag["class"]

    # FIX 2026-10-26: unwrap <section> i div.galley-rw (sirovi lektura HTML iz .chk)
    for sec in soup.find_all("section"):
        sec.unwrap()
    for _g in soup.find_all(class_="galley-rw"):
        _g.unwrap()


def _normalizuj(soup: BeautifulSoup) -> None:
    # div → p
    for div in soup.find_all("div"):
        if div.find(["div", "p", "ul", "ol", "table"]):
            continue
        if not div.get_text(strip=True):
            continue
        div.name = "p"

    # h4-h6 → h3
    for h in soup.find_all(["h4", "h5", "h6"]):
        h.name = "h3"

    # font → unwrap
    for font in soup.find_all("font"):
        font.unwrap()

    # center → p
    for c in soup.find_all("center"):
        p_new = soup.new_tag("p")
        for child in list(c.children):
            p_new.append(child)
        c.replace_with(p_new)

    # table layout → p
    for table in soup.find_all("table"):
        if len(table.find_all("tr")) <= 1:
            p_new = soup.new_tag("p")
            p_new.string = table.get_text(" ", strip=True)
            table.replace_with(p_new)

    # span bez stila → unwrap
    for span in soup.find_all("span"):
        if not span.get("style"):
            span.unwrap()

    # b→strong, i→em
    for b in soup.find_all("b"):
        b.name = "strong"
    for i in soup.find_all("i"):
        i.name = "em"

    # u,s,strike → unwrap
    for tag in soup.find_all(["u", "s", "strike", "del", "ins"]):
        tag.unwrap()

    # Deduplikacija: AAutorska → Autorska
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name in ("script", "style"):
            continue
        orig = str(text_node)
        new = re.sub(r"\b([A-ZŠĐČĆŽ])\1+([a-zšđčćž])", r"\1\2", orig)
        if new != orig:
            text_node.replace_with(new)


def _ukloni_duplikate_p(soup: BeautifulSoup) -> int:
    """Ukloni <p> ciji je pocetak prefix ili identican drugom <p>. Zadrzava duzi."""
    import re as _re

    def norm(t):
        t = _re.sub(r"^[\u2014\u2013\-\s]+", "", t.strip())
        return _re.sub(r"\s+", " ", t).lower()

    ps = soup.find_all("p")
    to_remove = []
    for i, p1 in enumerate(ps):
        t1 = p1.get_text(strip=True)
        if len(t1) < 30:
            continue
        n1 = norm(t1)
        for p2 in ps[i+1:]:
            t2 = p2.get_text(strip=True)
            if len(t2) < 30:
                continue
            n2 = norm(t2)
            mn = min(len(n1), len(n2))
            if mn < 60:
                continue
            if n1[:mn] == n2[:mn]:
                to_remove.append(p2 if len(t1) > len(t2) else p1)
                break
    for el in set(to_remove):
        if el.parent is not None:
            el.decompose()
    return len(to_remove)


def _skrati_overlap(prethodni, sljedeci, min_rijeci=15):
    """Ako kraj prethodnog = pocetak sljedeceg, skrati sljedeci za taj overlap.
    Vraca (skraceni_tekst, broj_uklonjenih_rijeci).
    Radi nad cistim tekstom (bez HTML)."""
    import re as _re
    def _words(t):
        return _re.sub(r"<[^>]+>", " ", t).split()
    w1 = _words(prethodni)
    w2 = _words(sljedeci) if False else _words(sljedeci)
    mn = min(len(w1), len(w2), 500)
    for L in range(mn, min_rijeci - 1, -1):
        if w1[-L:] == w2[:L]:
            # Skrati sljedeci za L rijeci; vrati ostatak
            return " ".join(w2[L:]), L
    return sljedeci, 0


_DEDUP_LOG_DIR = Path(__file__).resolve().parent.parent / ".logs"


def _dedup_log(knjiga, fajl, blok, rijeci, tekst, vrsta):
    """P0.5 (2026-11-06): jedna TSV linija po brisanju, prije primjene brisanja.
    .logs/dedup_<knjiga>.tsv: fajl, blok, rijeci, prvih 80 znakova, vrsta, vrijeme.
    Samo biljezi; ne utice na odluku o brisanju."""
    import datetime as _dt

    try:
        _s = re.sub(r"<[^>]+>", " ", str(tekst))
        _s = re.sub(r"\s+", " ", _s).strip()[:80]
        _ime = re.sub(r"[^\w.-]+", "_", str(knjiga)) or "knjiga"
        _DEDUP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_DEDUP_LOG_DIR / ("dedup_" + _ime + ".tsv"), "a", encoding="utf-8") as _f:
            _f.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (
                fajl, blok, rijeci, _s, vrsta,
                _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception:
        logger.exception("[dedup_log] upis nije uspio: %s / %s", knjiga, fajl)


def _je_duplikat(t1, t2, threshold=0.7):
    """Fuzzy match: 70%+ zajednickih rijeci (duzine >3)."""
    import re as _re
    w1 = set(w.lower() for w in _re.findall(r"\w+", t1) if len(w) > 3)
    w2 = set(w.lower() for w in _re.findall(r"\w+", t2) if len(w) > 3)
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= threshold


def _skrati_overlap_fuzzy(prethodni, sljedeci, prag=0.85, min_znakova=60, zadnjih=60):
    """2026-11-03: fuzzy overlap na razini odlomaka. Ako pocetak sljedeceg bloka
    priblizno (>=prag) ponavlja zadnje odlomke prethodnog, ukloni ih iz sljedeceg.
    Vraca (novi_sljedeci, broj_odlomaka, broj_rijeci); bez promjene (sljedeci, 0, 0)."""
    import difflib as _dl
    import html as _hh
    import re as _re

    def _norm(t):
        t = _re.sub(r"<[^>]+>", " ", t)
        return _re.sub(r"\W+", " ", _hh.unescape(t).lower()).strip()

    def _slican(a, b):
        if not a or not b:
            return False
        if a == b:
            return True
        sm = _dl.SequenceMatcher(None, a, b, autojunk=False)
        return (
            sm.real_quick_ratio() >= prag
            and sm.quick_ratio() >= prag
            and sm.ratio() >= prag
        )

    def _dijeli(t):
        tx, poz = [], []
        if "<p" in t.lower():
            for m in _re.finditer(r"<p[\s>].*?</p>", t, flags=_re.S | _re.I):
                n = _norm(m.group(0))
                if n:
                    tx.append(n)
                    poz.append(m.end())
            return tx, (lambda k: t[poz[k - 1]:])
        dijelovi = _re.split(r"\n\s*\n", t)
        for i, x in enumerate(dijelovi):
            n = _norm(x)
            if n:
                tx.append(n)
                poz.append(i)
        return tx, (lambda k: "\n\n".join(dijelovi[poz[k - 1] + 1:]))

    pt, _ = _dijeli(prethodni)
    nt, rez = _dijeli(sljedeci)
    if not pt or not nt:
        return sljedeci, 0, 0
    for j in range(max(0, len(pt) - zadnjih), len(pt)):
        if not _slican(pt[j], nt[0]):
            continue
        k = 0
        while j + k < len(pt) and k < len(nt) and _slican(pt[j + k], nt[k]):
            k += 1
        if j + k == len(pt) and sum(len(x) for x in nt[:k]) >= min_znakova:
            return rez(k), k, sum(len(x.split()) for x in nt[:k])
    return sljedeci, 0, 0


def _spoji_blokove(delovi):
    """Spoji blokove sa separatorom kad se spajaju dvije rijeci (alfanum na obje strane)."""
    if not delovi:
        return ""
    result = delovi[0]
    for b in delovi[1:]:
        if not b:
            continue
        last = result.rstrip()[-1] if result.rstrip() else ""
        first = b.lstrip()[0] if b.lstrip() else ""
        if last.isalnum() and first.isalnum():
            result += "\n"
        result += b
    return result



def _ukloni_dup_par(soup):
    """2026-11-06: brise PAR uzastopnih odlomaka koji se ponovi unutar 8 odlomaka
    (ponovljen dijalog u drugom stilu navodnika, retry bloka). Usporedba bez interpunkcije:
    prvi odlomak identican (>=8 rijeci), drugi identican ili sadrzan. Vraca broj obrisanih."""
    import re as _re
    ps = list(soup.find_all("p"))
    nt = [_re.sub(r"\W+", " ", p.get_text().lower()).strip() for p in ps]
    brisi = set()
    for i in range(1, len(ps)):
        if i in brisi or (i - 1) in brisi:
            continue
        a, b = nt[i - 1], nt[i]
        if len(a.split()) < 8 or not b:
            continue
        for j in range(max(1, i - 8), i - 1):
            if nt[j - 1] == a and nt[j] and (nt[j] == b or nt[j] in b or b in nt[j]):
                brisi.update((i - 1, i))
                break
    for k in sorted(brisi):
        ps[k].extract()
    if brisi:
        print("  [dup-par] obrisano odlomaka: %d" % len(brisi))
    return len(brisi)


def _crtica_navodnik_kraj(soup):
    """2026-11-06: tipografija vrati razmak oko crtice (ja—” -> ja — ”); poslije nje
    skini razmak izmedju crtice i zatvarajuceg navodnika. Nad tekstualnim cvorovima."""
    import re as _re
    from bs4 import NavigableString as _NS
    rx = _re.compile("\u2014[ \u00a0]+\u201d")
    n = 0
    for node in list(soup.find_all(string=True)):
        if type(node) is not _NS:
            continue
        if any(par.name in ("script", "style", "title") for par in node.parents):
            continue
        s = str(node)
        ns = rx.sub("\u2014\u201d", s)
        if ns != s:
            node.replace_with(ns)
            n += 1
    return n


def _ukloni_razmak_pred_zatvarajucim(soup):
    """2026-11-07: model ponekad zapise razmak/novi red ispred zatvarajuceg ”
    ('„Uspjesno.\n”'). Uklanja whitespace ispred ” u tekstualnim cvorovima,
    osim iza crtice (taj slucaj radi _navodnici_popravi). Vraca broj popravaka."""
    import re as _re_zn
    from bs4 import NavigableString as _NS_zn
    _rx = _re_zn.compile("(?<=[^\\s\u2014\u2013])\\s+\u201d")
    _br = 0
    for _n in list(soup.find_all(string=True)):
        if type(_n) is not _NS_zn:
            continue
        if any(_q.name in ("script", "style") for _q in _n.parents):
            continue
        _st = str(_n)
        _nv, _k = _rx.subn("\u201d", _st)
        if _k:
            _n.replace_with(_nv)
            _br += _k
    return _br


def _navodnici_popravi(soup):
    """2026-11-06: popravke tipicnih gresaka AI prevoda u navodnicima, nad tekstualnim
    cvorovima (cuva <em>). Samo kad je broj navodnika neparan:
    (A) izgubljen zatvarajuci ” ispred glagola govora: „Da, uzdahnuo -> „Da”, uzdahnuo
    (B) crtica usred pasusa umjesto otvarajuceg „: ... gotovo. — Dobro!” -> ... „Dobro!”
    (C) razmak izmedju crtice i ”: ' — ”' -> ' —”'
    Vraca broj popravaka."""
    import re as _re
    from bs4 import NavigableString as _NS
    _VERB = (r"(?:re\u010de|rekao|rekla|promrml\w+|izust\w+|prozbor\w+|odvrat\w+|upit\w+|zare\u017ea\w*|"
             r"dometn\w+|doda|dodao|dodala|povik\w+|uzdah\w+|uzdis\w+|\u0161apn\w+|prošapta\w*|zaurla\w*|"
             r"kresn\w+|zacvil\w+|dobac\w+|uzvikn\w+|vikn\w+|zapita\w+|zagun\u0111\w+|promuc\w+|prozbor\w+|zagrm\w+|prosikt\w+|uspi\w*|uspje\w*|zamisli\w+|razmi\u0161lja\w+|primijeti\w*|potvrdi\w*|prizna\w+|slagal\w+)")
    _rx_a = _re.compile("\u201e([^\u201e\u201d\"]{1,200}?)(?=,\\s+(?:[a-z\u010d\u0107\u017e\u0161\u0111]+\\s+)?" + _VERB + r"\b)")
    _rx_c = _re.compile("\u2014\\s+\u201d")
    _rx_c_kraj = _rx_c

    def _cv(p):
        return [n for n in p.find_all(string=True)
                if type(n) is _NS and not any(q.name in ("script", "style") for q in n.parents)]

    def _izmijeni(nodes, s, e, novo):
        poz = 0
        for idx, n in enumerate(nodes):
            ns = str(n); ln = len(ns)
            if s == e:
                ok = (poz <= s < poz + ln) or (idx == len(nodes) - 1 and s == poz + ln)
            else:
                ok = poz <= s and e <= poz + ln
            if ok:
                n.replace_with(ns[:s - poz] + novo + ns[e - poz:])
                return True
            poz += ln
        return False

    def _siroce(t):
        otv = False
        for i, ch in enumerate(t):
            if ch == "\u201e":
                otv = True
            elif ch == "\u201d":
                if otv:
                    otv = False
                else:
                    return i
        return -1

    ukupno = 0
    for p in soup.find_all("p"):
        # (C) neovisno o balansu navodnika
        for _ in range(3):
            _nodes = _cv(p)
            _t = "".join(str(n) for n in _nodes)
            _m = _rx_c_kraj.search(_t)
            if _m and _izmijeni(_nodes, _m.start() + 1, _m.end() - 1, ""):
                ukupno += 1
            else:
                break
        # (F) zavrsno '— „' -> '—”'
        _nodes = _cv(p)
        _t = "".join(str(n) for n in _nodes)
        _mf = _re.search("\\s*\u2014\\s*\u201e\\s*$", _t)
        if _mf and _izmijeni(_nodes, _mf.start(), _mf.end(), " \u2014\u201d"):
            ukupno += 1
        for _ in range(4):
            nodes = _cv(p)
            t = "".join(str(n) for n in nodes)
            o = t.count("\u201e")
            c = t.count("\u201d") + t.count("\u201c") + t.count('"')
            if o == c + 1:
                m = _rx_a.search(t)
                if m and _izmijeni(nodes, m.end(1), m.end(1), "\u201d"):
                    ukupno += 1
                    continue
                m = _re.search("(?<=rije\u010d )\u201e(\\w+)(?=[.,;])", t)
                if m and _izmijeni(nodes, m.end(1), m.end(1), "\u201d"):
                    ukupno += 1
                    continue
            if o == c + 1:
                _nx = p.find_next_sibling("p")
                _nt = _nx.get_text().lstrip() if _nx is not None else ""
                _ic, _io = _nt.find("\u201d"), _nt.find("\u201e")
                _nast = _ic != -1 and (_io == -1 or _ic < _io)
                _tr = t.rstrip()
                if (not _nast and _tr[-1:] in (".", "!", "?", "\u2026")
                        and _tr.rfind("\u201e") > _tr.rfind("\u201d")
                        and _izmijeni(nodes, len(_tr), len(_tr), "\u201d")):
                    ukupno += 1
                    continue
            if c == o + 1:
                m = _re.search("\u201d,\\s+" + _VERB + r"(?:\s+\w+){0,3},\s+(?=[a-z\u010d\u0107\u017e\u0161\u0111])", t)
                if (m and "\u201e" not in t[m.end():] and "\u201d" in t[m.end():]
                        and _izmijeni(nodes, m.end(), m.end(), "\u201e")):
                    ukupno += 1
                    continue
            if c > o and not t.lstrip().startswith(("\u2014", "\u2013")):
                i = _siroce(t)
                if i > 0:
                    k = t.rfind("\u2014 ", 0, i)
                    if (k >= 2 and t[k - 1] == " " and t[k - 2] in ".!?\u2026\u201d"
                            and not any(q in t[k:i] for q in "\u201e\u201d")
                            and _izmijeni(nodes, k, k + 2, "\u201e")):
                        ukupno += 1
                        continue
            m = _rx_c.search(t)
            if m and _izmijeni(nodes, m.start() + 1, m.end() - 1, ""):
                ukupno += 1
                continue
            break
    if ukupno:
        print("  [nav-fix] popravljeno navodnika: %d" % ukupno)
    return ukupno


def _apostrof_fix(soup):
    """2026-11-06: AI ponekad pretvori apostrof u otvarajuci navodnik (Skarling\u201es).
    Radi nad tekstualnim cvorovima: slovo + \u201e + malo slovo -> \u2019. Vraca broj izmjena."""
    import re as _re
    from bs4 import NavigableString as _NS
    _rx = _re.compile("(?<=[A-Za-z\u010d\u0107\u017e\u0161\u0111\u010c\u0106\u017d\u0160\u0110])\u201e(?=[a-z\u010d\u0107\u017e\u0161\u0111])")
    n = 0
    for node in list(soup.find_all(string=True)):
        if type(node) is not _NS:
            continue
        if any(par.name in ("script", "style", "title") for par in node.parents):
            continue
        nt = _rx.sub("\u2019", str(node))
        if nt != str(node):
            node.replace_with(nt)
            n += 1
    return n


def _popravi_fragment_pocetka(soup):
    """Odlomak koji pocinje malim slovom: prva recenica je odbacen rep
    prethodnog odlomka (prijelaz bloka pri prevodjenju). Ako prethodni
    odlomak vec zavrsava tim tekstom -> brise se; inace se dodaje prethodnom.
    Radi samo kad su id-evi uzastopni (jiN, jiN+1)."""
    import re as _re
    from bs4 import NavigableString as _NS

    rx = _re.compile(r'(.{1,200}?[.!?…]["”]?)(?=\s|$)')

    def _num(p):
        m = _re.search(r"(\d+)$", p.get("id") or "")
        return int(m.group(1)) if m else None

    def _norm(s):
        return _re.sub(r"[\W_]+", "", s.lower())

    n_drop = n_move = 0
    for cur in list(soup.find_all("p")):
        prev = cur.find_previous_sibling("p")
        if prev is None or not cur.contents:
            continue
        a, b = _num(prev), _num(cur)
        if a is None or b is None or b != a + 1:
            continue
        first = cur.contents[0]
        if not isinstance(first, _NS):
            continue
        st = str(first).lstrip()
        if not st or not st[0].isalpha() or not st[0].islower():
            continue
        m = rx.match(st)
        if not m:
            continue
        frag = m.group(1)
        if len(frag.split()) > 15:
            continue
        if _norm(prev.get_text()).endswith(_norm(frag)) and len(_norm(frag)) >= 5:
            akcija = "brisem (ponovljen rep)"
            n_drop += 1
        else:
            nodes = prev.find_all(string=True)
            if not nodes:
                continue
            last = nodes[-1]
            ls = str(last).rstrip()
            if not ls.endswith(".") or ls.endswith("…"):
                print(f"  [frag-fix] preskoceno {cur.get('id')}: prethodni ne zavrsava tackom")
                continue
            last.replace_with(ls[:-1] + " " + frag)
            akcija = "dodajem prethodnom"
            n_move += 1
        rest = st[len(frag):].lstrip()
        if rest:
            first.replace_with(rest)
        elif len(cur.contents) == 1:
            cur.decompose()
        else:
            first.extract()
        print(f"  [frag-fix] {cur.get('id')}: {akcija}: {frag[:50]}")
    if n_drop or n_move:
        print(f"  [frag-fix] obrisano: {n_drop}, premjesteno: {n_move}")
    return n_drop + n_move


def _stil_ocisti_p(soup):
    """2026-11-06: (1) spaja <p> presjecen usred recenice (prethodni bez zavrsetka,
    sljedeci pocinje malim slovom); (2) brise identican odlomak (>=20 rijeci) ako se
    ponovi unutar 12 odlomaka. Radi nad BeautifulSoup cvorovima. Idempotentno.
    Vraca (spojeno, uklonjeno)."""
    import re as _re
    from bs4 import NavigableString as _NS
    _KRAJ = set(".!?:;)]*'\"") | {"\u2026", "\u201d", "\u201c", "\u00bb", "\u2014", "\u2013", "\u2019"}

    def _sljedeci_p(el):
        n = el.next_sibling
        while n is not None and isinstance(n, _NS) and not str(n).strip():
            n = n.next_sibling
        return n if getattr(n, "name", None) == "p" else None

    gone = set()
    spojeno = 0
    for p in list(soup.find_all("p")):
        if id(p) in gone:
            continue
        while True:
            n = _sljedeci_p(p)
            if n is None:
                break
            tp = p.get_text().rstrip()
            tn = n.get_text().lstrip()
            if not tp or not tn:
                break
            if tp[-1] in _KRAJ or not tn[0].islower():
                break
            if p.find("img") is not None or n.find("img") is not None:
                break
            if not tp.endswith("-"):
                p.append(_NS(" "))
            for c in list(n.contents):
                p.append(c.extract())
            n.extract()
            gone.add(id(n))
            spojeno += 1

    def _norm(t):
        return _re.sub(r"\W+", " ", t.lower()).strip()

    vidjeni = []
    uklonjeno = 0
    for p in list(soup.find_all("p")):
        if id(p) in gone:
            continue
        nt = _norm(p.get_text())
        if len(nt.split()) >= 20 and nt in vidjeni[-12:]:
            p.extract()
            gone.add(id(p))
            uklonjeno += 1
            continue
        vidjeni.append(nt)
    if spojeno or uklonjeno:
        print("  [p-fix] spojeno presjecenih: %d, uklonjeno duplikata: %d" % (spojeno, uklonjeno))
    return spojeno, uklonjeno

def _razdvoji_dijalog_p(soup: BeautifulSoup) -> int:
    """Razdvoji <p> sa 3+ replika (em-crtica posle .!?…) u zasebne <p>."""
    import re as _re

    changes = 0
    for p in list(soup.find_all("p")):
        text = p.get_text()
        if len(text) < 200 or text.count("\u2014") < 3:
            continue
        parts = _re.split(r"(?<=[.!?\u2026])\s*(?=\u2014\s)", text.strip())
        if len(parts) <= 1:
            continue
        parent = p.parent
        if parent is None:
            continue
        idx = list(parent.children).index(p) if p in parent.children else -1
        if idx < 0:
            continue
        p.clear()
        p.append(parts[0])
        insert_at = idx + 1
        for part in parts[1:]:
            new_p = soup.new_tag("p")
            new_p.append(part.strip())
            parent.insert(insert_at, new_p)
            insert_at += 1
        changes += 1
    return changes


def _dodaj_vijenac(soup: BeautifulSoup) -> None:
    b64 = _png_b64(CENTER_ORNAMENT_PNG)
    body = soup.find("body")
    if not body:
        return
    if b64:
        html = (
            f'<img class="booklyfi-vijenac" '
            f'src="data:image/png;base64,{b64}" '
            f'style="display:block;width:70%;height:auto;'
            f'margin:0.5em auto 0.8em auto;" />'
        )
    else:
        html = '<p class="booklyfi-vijenac" style="text-align:center;">— ✠ —</p>'
    orn = BeautifulSoup(html, "html.parser").find(["img", "p"])
    body.insert(0, copy.deepcopy(orn))


SKIP_FNAME = (
    "cover",
    "titlepage",
    "title_page",
    "copyright",
    "colophon",
    "toc",
    "contents",
    "nav",
    "impressum",
    "about",
    "acknowledg",
    "dedication",
    "epigraph",
    "foreword",
    "preface",
    "introduction",
)


SKIP_FIRST_P = (
    "naslov izvornika",
    "autorska prava",
    "copyright",
    "sadržaj",
    "uvod",
    "predgovor",
    "posveta",
    "zahvala",
    "bilješka",
    "napomena",
    "izvorni naslov",
    "izvorno izdanje",
    "originalno izdanje",
)


_DEBUG_JE_POGLAVLJE = False  # isključeno


def _read(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _img_popravi(files: dict[str, bytes]) -> int:
    """XHTML 1.1: img mora imati alt i ne smije biti dijete body-ja (omotac div)."""
    n = 0
    for name in list(files.keys()):
        if not name.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        raw = files[name]
        if b"<img" not in raw:
            continue
        try:
            soup = BeautifulSoup(raw.decode("utf-8"), "html.parser")
        except Exception:
            continue
        izm = False
        for im in soup.find_all("img"):
            if im.get("alt") is None:
                im["alt"] = ""
                izm = True
            if im.parent is not None and im.parent.name == "body":
                w = soup.new_tag("div")
                w["style"] = "text-align:center;"
                im.wrap(w)
                izm = True
        if izm:
            files[name] = str(soup).encode("utf-8")
            n += 1
    return n


def _write(path: Path, files: dict[str, bytes]) -> None:
    tmp_fd, tmp = tempfile.mkstemp(suffix=".epub.tmp", dir=path.parent)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            if "mimetype" in files:
                z.writestr(
                    zipfile.ZipInfo("mimetype"),
                    files["mimetype"],
                    compress_type=zipfile.ZIP_STORED,
                )
        with zipfile.ZipFile(tmp, "a", zipfile.ZIP_DEFLATED) as z:
            for n, d in files.items():
                if n == "mimetype":
                    continue
                z.writestr(n, d)
        os.close(tmp_fd)
        shutil.move(tmp, str(path))
    except Exception:
        try:
            os.close(tmp_fd)
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _meta(files: dict) -> tuple[str, str]:
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                s = BeautifulSoup(d, "xml")
                t = s.find("dc:title")
                c = s.find("dc:creator")
                return (
                    c.get_text(strip=True) if c else "Nepoznat_autor",
                    t.get_text(strip=True) if t else "Nepoznat_naslov",
                )
            except Exception:
                logger.exception("[C1_http] styler.py:320 Exception")
    return "Nepoznat_autor", "Nepoznat_naslov"


def _san(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "", s.strip())
    return re.sub(r"\s+", "_", s)


def _ime(c: str, t: str) -> str:
    return f"{_san(c)}_{_san(t)}_PREVEDENO_STYLED.epub"


SKIP_TITLES = (
    "sadržaj",
    "sadrzaj",
    "table of contents",
    "contents",
    "toc",
    "impresum",
    "copyright",
    "autorska prava",
    "sva prava",
    "naslovna",
    "title page",
    "cover",
    "korice",
    "kazalo",
    "index",
)


def _je_poglavlje(html_bytes, full_path):
    def _dbg(r):
        if _DEBUG_JE_POGLAVLJE:
            logger.info("[styler] _je_poglavlje ODBIJEN %s: %s", full_path, r)

    if len(html_bytes) < 2000:
        _dbg("prekratak HTML")
        return False

    basename = Path(full_path).name.lower()
    if any(s in basename for s in SKIP_FNAME):
        _dbg("basename: " + basename)
        return False

    try:
        soup = BeautifulSoup(
            html_bytes.decode("utf-8", errors="replace"), "html.parser"
        )
    except Exception as e:
        _dbg("BS: " + str(e))
        return False

    text = soup.get_text(strip=True)
    if len(text) < 500:
        _dbg("prekratak tekst")
        return False

    title = ""
    for tag in ("h1", "h2", "h3", "title"):
        t = soup.find(tag)
        if t and t.get_text(strip=True):
            title = t.get_text(strip=True)
            break

    tl = title.lower().strip()
    for skip in SKIP_TITLES:
        if tl == skip or tl.startswith((skip + " ", skip + ":")):
            return False

    fp = soup.find("p")
    if fp:
        fpl = fp.get_text(strip=True).lower()[:100]
        for skip in SKIP_FIRST_P:
            if fpl.startswith(skip):
                _dbg("first_p: " + fpl)
                return False

    return True


def _izvuci_toc_mapu(files, opf_dir):
    mapa = {}
    for n in files:
        if not n.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        try:
            s = BeautifulSoup(files[n], "html.parser")
            nav = s.find("nav", attrs={"epub:type": "toc"})
            if not nav:
                continue
            for a in nav.find_all("a"):
                nas = a.get_text(strip=True)
                href = a.get("href", "").split("#")[0]
                if nas and href:
                    if opf_dir and not href.startswith(opf_dir):
                        href = (
                            (opf_dir + "/" + href)
                            if not href.startswith("/")
                            else href.lstrip("/")
                        )
                    mapa[href] = nas
            if mapa:
                return mapa
        except Exception:
            logger.exception("[C1_kriticno] styler.py:426 Exception")

    ncx = next((n for n in files if n.lower().endswith(".ncx")), None)
    if ncx:
        try:
            soup = BeautifulSoup(files[ncx], "xml")
            for nav in soup.find_all("navPoint"):
                lab = nav.find("navLabel")
                con = nav.find("content")
                if lab and con:
                    nas = lab.get_text(strip=True)
                    s2 = con.get("src", "").split("#")[0]
                    if nas and s2:
                        if opf_dir and not s2.startswith(opf_dir):
                            s2 = (
                                (opf_dir + "/" + s2)
                                if not s2.startswith("/")
                                else s2.lstrip("/")
                            )
                        mapa[s2] = nas
            if mapa:
                return mapa
        except Exception:
            logger.exception("[C1_kriticno] styler.py:449 Exception")
    return mapa


def _dodaj_naslov(soup, broj, naslov=None):
    body = soup.find("body")
    if not body:
        return

    nasao_tekst = False
    for child in list(body.children):
        if not hasattr(child, "name"):
            continue
        if child.name in ("h1", "h2", "h3"):
            if not nasao_tekst:
                child.decompose()
            continue
        if child.name == "p" and len(child.get_text(strip=True)) > 50:
            nasao_tekst = True
            break

    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = naslov if naslov else ("POGLAVLJE %d" % broj)

    insert_pos = 0
    for i, child in enumerate(body.children):
        cls = child.get("class") if hasattr(child, "get") else None
        if cls:
            if isinstance(cls, str):
                cls = cls.split()
            if "booklyfi-vijenac" in cls:
                insert_pos = i + 1
                continue
        break
    body.insert(insert_pos, h1)


def _dodaj_dropcap(soup):
    from bs4 import NavigableString

    # FIX 2026-10-26: Dropcap ide SAMO u prvi <p> posle <h1>.
    # Ako je taj <p> dijalog (— " „), PRESKOČI dropcap za celo poglavlje
    # (ne idi dalje — inače završi na pola stranice).
    body = soup.find("body")
    if not body:
        return False

    # F0.11: nadji prvi <p> sa >=60c teksta (preskoci kratke naslove prica)
    prvi_p = None
    h1 = body.find("h1")
    if h1:
        for kandidat in h1.find_all_next("p"):
            t = kandidat.get_text(strip=True)
            if len(t) >= 60 and not t.isdigit():
                prvi_p = kandidat
                break
    if prvi_p is None:
        for kandidat in body.find_all("p"):
            t = kandidat.get_text(strip=True)
            if len(t) >= 60 and not t.isdigit():
                prvi_p = kandidat
                break

    if prvi_p is None:
        return False

    _cls_ranije = prvi_p.get("class") or []
    if isinstance(_cls_ranije, str):
        _cls_ranije = _cls_ranije.split()
    if "booklyfi-prvi" in _cls_ranije:
        return False

    prvi_tekst = prvi_p.get_text(strip=True)
    prvi_char = prvi_tekst[0] if prvi_tekst else ""
    dijalog_chars = ("—", "–", "-", "‒", "―", '"', "„", '"', '"', "«", "'")

    if prvi_char in ('"', "\u201e", "\u201c", "\u201d", "\u00ab", "'"):
        # P2.12: govor u navodnicima na početku poglavlja: bez dropcapa i bez umjetne crtice
        prvi_p["class"] = list(_cls_ranije) + ["booklyfi-prvi"]
        return False

    if prvi_char in dijalog_chars:
        # F0.11: dijalog na pocetku — velika crtica umesto slova
        if prvi_char in ("—", "–", "‒", "―"):
            crtica = prvi_char
        else:
            crtica = "—"
        img_html = (
            '<span class="booklyfi-crtica" '
            'style="float:left;display:block;'
            'font-size:4em;line-height:0.8;'
            'margin:0.1em 0.05em 0 0;padding:0;">'
            + crtica
            + '</span>'
        )
        cls = prvi_p.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        crtica_tag = BeautifulSoup(img_html, "html.parser").find("span")
        if prvi_char in ("\u2014", "\u2013", "\u2012", "\u2015", "-"):
            for _n in prvi_p.find_all(string=True):
                _s = str(_n)
                if _s.strip():
                    _i = len(_s) - len(_s.lstrip())
                    if _s[_i] == prvi_char:
                        _n.replace_with(NavigableString(_s[:_i] + _s[_i + 1:]))
                    break
        prvi_p.insert(0, crtica_tag)
        prvi_p["class"] = list(cls) + ["booklyfi-prvi"]
        return True

    # Primeni dropcap SAMO na prvi_p
    for p in [prvi_p]:
        cls = p.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        if "booklyfi-naslov" in cls or "booklyfi-prvi" in cls:
            continue

        text = p.get_text(strip=True)
        if len(text) < 60 or text.isdigit():
            continue

        prvo = None
        cvor = None
        for desc in p.descendants:
            if not isinstance(desc, NavigableString):
                continue
            s = str(desc)
            for i, ch in enumerate(s):
                if ch.isalpha():
                    prvo = ch.upper()
                    cvor = (desc, i)
                    break
            if prvo:
                break

        if not prvo:
            continue

        fname = DROPCAP_MAP.get(prvo)
        if not fname:
            continue
        b64 = _png_b64(fname)
        if not b64:
            continue

        desc_node, idx = cvor
        s_orig = str(desc_node)
        desc_node.replace_with(NavigableString(s_orig[:idx] + s_orig[idx + 1 :]))

        img_html = (
            '<img class="booklyfi-dropcap" '
            'src="data:image/png;base64,' + b64 + '" '
            'style="float:left;display:block;'
            "width:4em;height:auto;max-width:none;"
            "margin:0.1em 0.15em 0 0;padding:0;"
            'vertical-align:top;" />'
        )
        skriveno_html = (
            '<span style="font-size:1px;color:transparent;line-height:0;">'
            + prvo
            + "</span>"
        )
        img_tag = BeautifulSoup(img_html, "html.parser").find("img")
        skriveno_tag = BeautifulSoup(skriveno_html, "html.parser").find("span")

        p.insert(0, skriveno_tag)
        p.insert(0, img_tag)
        p["class"] = list(cls) + ["booklyfi-prvi"]
        return True

    return False


# def _ekstrahuj_zajednicke_slike(files: dict) -> list[str]:
    """
    2026-10-24 B7: dedup inline base64 slike u zajednicke PNG/JPG fajlove.
    Zamena src="data:image/png;base64,XXX" sa relativnim putem do PNG-a.
    Vraca listu novih putanja (za OPF manifest).
    """
    import base64 as _b64_b7
    import hashlib as _hl_b7
    import os as _os_b7

    RX = re.compile(r"data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=]+)")
    EXT_MAP = {"png": "png", "jpeg": "jpg", "jpg": "jpg"}

    unique: dict[str, bytes] = {}
    b64_hash_ext: dict[str, tuple] = {}

    for name, data in files.items():
        if not name.endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        for m in RX.finditer(text):
            fmt = m.group(1).lower()
            b64 = m.group(2)
            if b64 in b64_hash_ext:
                continue
            try:
                raw = _b64_b7.b64decode(b64, validate=False)
            except Exception:
                continue
            h = _hl_b7.sha256(raw).hexdigest()[:16]
            ext = EXT_MAP.get(fmt, "png")
            unique[h] = raw
            b64_hash_ext[b64] = (h, ext)

    if not unique:
        return []

    new_paths: list[str] = []
    for h, raw in unique.items():
        ext = next((e for (hh, e) in b64_hash_ext.values() if hh == h), "png")
        path = f"images/booklyfi-shared-{h}.{ext}"
        if path not in files:
            files[path] = raw
            new_paths.append(path)

    for name in list(files.keys()):
        if not name.endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            text = files[name].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        dirname = _os_b7.path.dirname(name) or "."

        def _repl(m, _dirname=dirname):
            b64 = m.group(2)
            h, ext = b64_hash_ext[b64]
            png_path = f"images/booklyfi-shared-{h}.{ext}"
            return _os_b7.path.relpath(png_path, _dirname)

        new_text = RX.sub(_repl, text)
        if new_text != text:
            files[name] = new_text.encode("utf-8")

    return new_paths



# ═══════════════════════════════════════════════════════════════════════════
# V7 OVERRIDES — popravke za posvetu, discovery, h1 duplikate, \uFFFC
# ═══════════════════════════════════════════════════════════════════════════


def _ocisti_fffc(soup):
    """Ukloni \ufffc (object replacement) iz svih tekstualnih čvorova."""
    for tn in soup.find_all(string=True):
        s = str(tn)
        if "\ufffc" in s:
            tn.replace_with(s.replace("\ufffc", ""))
    return soup


# ═══════════════════════════════════════════════════════════════════════════
# NASLOVI v2 (P2.16, 2026-11-12)
# Uzrok iz dijagnoze: h1 je dobivao (a) naslov knjige iz <title> (Prince of Thorns),
# (b) naziv fajla iz TOC-a ("Part0000 Split 003", "The Savage T-F Solomon Kane Split 4"),
# (c) placeholder "[[NEPREVEDENO: blok 0]]", dok je pravi naslov poglavlja ostajao
# kao kratki <p> u tijelu (broj "2", "Obmana", "Desna ruka propasti"). Nav/NCX su
# pisali "POGLAVLJE <redni broj fajla>", pa TOC nije odgovarao h1.
# Sada: naslov = lose-provjera -> naslov iz tijela -> TOC -> h1 u fajlu -> <title>
# -> "POGLAVLJE n". _dodaj_naslov VRACA tekst h1, a TOC koristi isti tekst.
# ═══════════════════════════════════════════════════════════════════════════

_NASLOV_LOS_RX = re.compile(
    r"(?i)(\bsplit[\s_\-]*\d+|\bpart\d{3,}|\bdummy\b|\bindex[\s_\-]*\d+"
    r"|\.x?html?$|neprevedeno|^\[\[|^onbekend$|^untitled$|^unknown$)"
)
_NASLOV_BROJ_RX = re.compile(r"^(\d{1,3}|[IVXLC]{1,7})\.?$")
_NASLOV_BROJ_RIJEC_RX = re.compile(
    r"(?i)^(?:chapter|poglavlje|glava|ch\.?)\s+(\d{1,3}|[IVXLC]{1,7})\.?$"
)
_NASLOV_KRAJ_RX = re.compile(r'[.!?\u2026,;:"\u201d\u201c\u00bb\u00ab)\u2019]$')


def _norm_naslov(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (t or "").lower())).strip()


_NASLOV_PREVOD = {}  # norm(EN podnaslov) -> HR podnaslov, uci se iz poglavlja "5" + "Cetiri godine ranije"
_NASLOV_EN_CH_RX = re.compile(r"(?i)^(?:chapter|poglavlje|ch\.?)\s+(\d{1,3})\s*[-\u2013\u2014:]\s*(.+)$")


def _naslov_en_chapter(t):
    m = _NASLOV_EN_CH_RX.match((t or "").strip())
    return (m.group(1), m.group(2).strip()) if m else None


def _naslov_lose(t, knjiga=""):
    """True ako tekst ne smije biti naslov poglavlja: prazan, naziv fajla,
    placeholder ili naslov cijele knjige."""
    t = re.sub(r"\s+", " ", (t or "").replace("\ufffc", "")).strip()
    if not t:
        return True
    if _NASLOV_LOS_RX.search(t):
        return True
    if knjiga:
        nk = _norm_naslov(knjiga)
        nt = _norm_naslov(t)
        if nk and nt and (nt == nk or (nk in nt and len(nt) <= len(nk) + 8)):
            return True
    return False


def _p_tekst(el):
    s = el.get_text(" ", strip=True).replace("\ufffc", "").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _je_naslovni_tekst(t):
    """Kratak odlomak bez zavrsne interpunkcije = kandidat za naslov."""
    if not t or len(t) > 80 or len(t.split()) > 10:
        return False
    if not re.search(r"\w", t):  # separatori: "*", "---"
        return False
    if _NASLOV_LOS_RX.search(t):  # "[[NEPREVEDENO: blok 0]]", naziv fajla
        return False
    if _NASLOV_KRAJ_RX.search(t):
        return False
    if re.match(r"^[\u2014\u2013\-\u201e\"\u201c\u00ab\u2018']", t):  # dijalog
        return False
    return True


def _je_broj_naslova(t):
    return bool(_NASLOV_BROJ_RX.match(t) or _NASLOV_BROJ_RIJEC_RX.match(t))


def _naslov_iz_tijela(body):
    """Pravi naslov poglavlja koji je ostao kao kratki <p> na pocetku tijela.
    Vraca (tekst_h1, [p elementi za brisanje], vrsta, broj) ili None.
    vrsta: 'broj+naslov' ("5" + "Cetiri godine ranije"), 'broj' ("12"), 'naslov' ("Obmana").
    Prvi neprazni <p> mora biti kratak i bez zavrsne interpunkcije; "*" i dijalog prekidaju."""
    parts = []
    for el in body.find_all("p"):
        if "booklyfi-vijenac" in (el.get("class") or []):
            continue  # ornament-fallback "— ✠ —" kad nema PNG-a
        t = _p_tekst(el)
        if not t:
            continue
        parts.append((el, t))
        if len(parts) == 2:
            break
    if not parts:
        return None
    el1, t1 = parts[0]
    if not _je_naslovni_tekst(t1):
        return None
    mc = re.match(r"^(\d{1,3})\s+([A-Z\u010c\u0106\u017d\u0160\u0110][^\n]{2,70})$", t1)
    if mc:
        return ("POGLAVLJE " + mc.group(1) + " \u2013 " + mc.group(2), [el1], "broj+naslov", mc.group(1))
    m = _NASLOV_BROJ_RX.match(t1) or _NASLOV_BROJ_RIJEC_RX.match(t1)
    if m:
        br = m.group(1).upper()
        lab = "POGLAVLJE " + br
        if len(parts) == 2:
            el2, t2 = parts[1]
            if _je_naslovni_tekst(t2) and not _je_broj_naslova(t2):
                return (lab + " \u2013 " + t2, [el1, el2], "broj+naslov", br)
        return (lab, [el1], "broj", br)
    return (t1, [el1], "naslov", "")


def _odvoji_broj_prefiks(body):
    """Broj poglavlja spojen s prvim odlomkom ("12 Prije cetiri godine...") ->
    ukloni prefiks iz teksta i vrati broj (string) ili None. Samo 1-3 znamenke
    ispred velikog slova/navodnika, tako da godine ("1066 ...") ostaju netaknute."""
    from bs4 import NavigableString

    for el in body.find_all("p"):
        if "booklyfi-vijenac" in (el.get("class") or []):
            continue
        t = _p_tekst(el)
        if not t:
            continue
        if len(t) < 40:
            return None
        for n in el.find_all(string=True):
            s = str(n)
            if not s.strip():
                continue
            m = re.match(
                r"^\s*(\d{1,3})\s+(?=[A-Z\u010c\u0106\u017d\u0160\u0110\u201e\"\u201c\u00ab])", s
            )
            if m:
                n.replace_with(NavigableString(s[m.end():]))
                return m.group(1)
            return None
        return None
    return None


def _razdvoji_literalne_nl(soup):
    """Doslovni znakovi backslash+n u tekstu odlomka (ostatak JSON-a iz .chk, npr.
    'rijec.\\n\\nSljedeci odlomak') -> pravi odlomci. Odlomke s ugnijezdenim tagovima
    ne dira. Vraca broj razdvojenih odlomaka."""
    n_split = 0
    for tn in list(soup.find_all(string=True)):
        if tn.parent is not None and tn.parent.name in ("style", "script"):
            continue
        s = str(tn)
        if "\\u" in s:
            ns = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
            if ns != s:
                tn.replace_with(ns)
                par = tn.parent if hasattr(tn, "parent") else None
    for p in list(soup.find_all("p")):
        if not p.find(True) and "\u00a0" in p.get_text() and not p.get_text().replace("\u00a0", "").strip():
            p.decompose()
        if p.find(True):
            continue
        s = p.get_text()
        if "\\n" not in s:
            continue
        dijelovi = [x.strip() for x in re.split(r"(?:\s*\\n\s*)+", s) if x.strip()]
        if not dijelovi:
            p.string = ""
            continue
        p.string = dijelovi[0]
        if len(dijelovi) < 2:
            continue
        prev = p
        for d in dijelovi[1:]:
            novi = soup.new_tag("p")
            if p.get("class"):
                novi["class"] = list(p.get("class"))
            novi.string = d
            prev.insert_after(novi)
            prev = novi
        n_split += 1
    return n_split


def _dodaj_naslov(soup, broj, naslov=None, knjiga=""):
    """v2: vraca tekst h1 koji je upisan/ostavljen (None = bez naslova).
    Prioritet: lose-provjera -> broj+naslov iz tijela -> naslov (TOC) -> dobar h1 u fajlu
    -> naslov/broj iz tijela -> broj spojen s odlomkom -> <title> -> POGLAVLJE n."""
    body = soup.find("body")
    if not body:
        return None

    # FIX 2026-10-26: TOC naslov moze biti "Pitanja\nPoradili su mu na ruci…"
    # — spojen naslov + prva recenica iz .chk. Uzmi samo prvu liniju kao naslov
    # i ukloni je iz prvog <p> da dropcap ne uzme slovo iz naslova.
    if naslov and "\n" in naslov:
        prva = naslov.split("\n")[0].strip()
        if prva and len(prva) < 60:
            for _p in body.find_all("p"):
                if _p.find(True):
                    continue
                _t = _p.get_text()
                if _t.lstrip().startswith(prva):
                    _rest = _t.lstrip()[len(prva):].lstrip("\n\r \t")
                    if _rest:
                        _p.clear()
                        _p.append(_rest)
                        naslov = prva
                    break

    if naslov and _naslov_lose(naslov, knjiga):
        naslov = None

    lead = _naslov_iz_tijela(body)
    h1_stari = body.find("h1")
    h1_tekst = re.sub(r"\s+", " ", h1_stari.get_text(" ", strip=True)).strip() if h1_stari else ""
    h1_dobar = bool(h1_stari) and not _naslov_lose(h1_tekst, knjiga)

    final = None
    brisi = []
    zadrzi_h1 = False

    if lead and lead[2] == "broj+naslov":
        final, brisi = lead[0], list(lead[1])
        _en = _naslov_en_chapter(naslov) if naslov else None
        if _en and " \u2013 " in final:
            _NASLOV_PREVOD[_norm_naslov(_en[1])] = final.split(" \u2013 ", 1)[1]
    elif naslov:
        final = naslov.strip()
        _en = _naslov_en_chapter(final)
        if _en and not lead:
            # engleski TOC naslov ("Chapter 12 - Four years earlier"): bez engleskog teksta u knjizi
            _sub = _NASLOV_PREVOD.get(_norm_naslov(_en[1]))
            final = "POGLAVLJE %s" % _en[0] + (" \u2013 " + _sub if _sub else "")
        if not lead:
            _odvoji_broj_prefiks(body)
        if lead:
            if lead[2] == "naslov" and _norm_naslov(lead[0]) == _norm_naslov(final):
                brisi = list(lead[1])
            elif lead[2] == "broj" and re.search(r"(?<!\w)%s(?!\w)" % re.escape(lead[3]), final, re.I):
                brisi = list(lead[1])
    elif h1_dobar:
        final = h1_tekst
        zadrzi_h1 = True
        if not lead:
            _odvoji_broj_prefiks(body)
        if lead and lead[2] == "naslov" and _norm_naslov(lead[0]) == _norm_naslov(final):
            brisi = list(lead[1])
    elif lead:
        final, brisi = lead[0], list(lead[1])
    else:
        br = _odvoji_broj_prefiks(body)
        if br:
            final = "POGLAVLJE " + br

    if final is None:
        if len(body.get_text(strip=True)) < 400:
            if h1_stari and not h1_dobar:
                for h in body.find_all("h1"):
                    h.decompose()
            return None
        # F0.36: Stroga validacija <title> taga (nikad naslov knjige / naziv fajla)
        _title_tag = soup.find("title")
        if _title_tag:
            _t = _title_tag.get_text(strip=True)
            if (
                _t
                and len(_t) <= 60
                and len(_t.split()) <= 10
                and not _t.endswith("…")
                and not _t.endswith(".")
                and _t.lower() not in ("navigation", "cover", "toc")
                and _t not in ("A Little Hatred", "The Trouble With Peace", "The Wisdom of Crowds")
                and not _naslov_lose(_t, knjiga)
                and not re.match(r"(?i)^(?:part|chapter|ch\.?|poglavlje|section)\s*\d+$", _t)
            ):
                final = _t
        if final is None:
            final = "POGLAVLJE %d" % broj

    for el in brisi:
        if el.parent is not None:
            el.decompose()

    if zadrzi_h1:
        return final

    for h in body.find_all("h1"):
        h.decompose()
    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = final
    insert_pos = 0
    for i, child in enumerate(body.children):
        cls = child.get("class") if hasattr(child, "get") else None
        if cls:
            if isinstance(cls, str):
                cls = cls.split()
            if "booklyfi-vijenac" in cls:
                insert_pos = i + 1
                continue
        break
    body.insert(insert_pos, h1)

    # F0.17: ako je prvi <p> posle h1 identican naslovu, obrisi ga
    _prvi_p = h1.find_next("p")
    if _prvi_p and _prvi_p.get_text(strip=True) == h1.get_text(strip=True):
        _prvi_p.decompose()

    # FIX 2026-11-11: naslov je kratki token (npr. broj "8"), a prvi <p> pocinje
    # istim tokenom ("8 Sjedili smo...") -> ukloni ga da dropcap ide na pravo slovo.
    _nas = (final or "").strip()
    if _nas and len(_nas) <= 6:
        import re as _re_nas
        from bs4 import NavigableString as _NS_nas
        for _p in h1.find_all_next("p"):
            _nodes = [_n for _n in _p.find_all(string=True) if str(_n).strip()]
            if not _nodes:
                continue
            _n0 = _nodes[0]
            _s0 = str(_n0)
            if _s0.strip() == _nas:
                _n0.replace_with(_NS_nas(""))
            else:
                _m0 = _re_nas.match(r"^\s*" + _re_nas.escape(_nas) + r"\s+(?=\S)", _s0)
                if _m0:
                    _n0.replace_with(_NS_nas(_s0[_m0.end():]))
            break
    return final




def _zavrsava_url_ili_domenom(tekst):
    """F0.18b izuzetak: blok koji zavrsava URL-om/domenom (npr. stranica 'O autoru')
    nije prekinut prevod, jer URL nema zavrsnu interpunkciju."""
    import re as _re_url
    t = (tekst or "").strip()
    if not t:
        return False
    zadnji = t.split()[-1]
    return bool(_re_url.search(
        r"(https?://|www\.)\S+|[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.(com|org|net|info|edu|gov|io|co|hr|ba|rs|me|uk)(/\S*)?$",
        zadnji, _re_url.IGNORECASE))


def run_epub_styler(
    epub_path, output_path=None, fleet=None, log_callback=None, options=None
):
    import datetime as _dt
    import html as _html
    import re as _re

    epub_path = Path(epub_path)

    def _log(msg, atype="info"):
        logger.info("[styler] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    def _esc(s):
        return _html.escape(str(s or ""), quote=True)

    def _page(title, body_html):
        css = (
            "body{background:#FDF6E3;color:#3E2723;font-family:Georgia,serif;"
            "margin:0 8%;padding:3em 0;line-height:1.7;font-size:1em;}"
            "h1,h2{color:#5D4037;}h1{text-align:center;font-size:1.5em;}"
            "hr{border:none;border-top:1px solid #8B6914;width:40%;margin:2em auto;}"
            "ul{list-style:none;padding:0;}"
            "li{padding:0.4em 0;border-bottom:1px dotted #8B6914;}"
            "a{color:#3E2723;text-decoration:none;}"
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
            '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">'
            '<head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
            "<title>" + _esc(title) + "</title>"
            '<style type="text/css">' + css + "</style></head><body>" + body_html + "</body></html>"
        )

    GENERIC_RX = _re.compile(
        r"^(?:part\s*\d+|chapter\s*\d+|ch\.?\s*\d+|"
        r"poglavlje\s*\d+|odjeljak\s*\d+|section\s*\d+|"
        r"book\s*\d+|knjiga\s*\d+)$",
        _re.I,
    )

    DEDICATION_STARTS = (
        "za ",
        "za\u00a0",
        "posve",
        "dedicat",
        "in memory",
        "u sje\u0107anje",
        "u spomen",
        "for ",
    )

    def _je_posveta(tlow, tlen):
        if tlen > 400:
            return False
        s = tlow.strip()
        for pfx in DEDICATION_STARTS:
            if s.startswith(pfx):
                return True
        return False

    def _naslov_iz(hb, toc_naslov, book_title):
        # F0.37: Stroga validacija naslova (ne smije biti recenica)
        INVALID_TITLES = {"A Little Hatred", "The Trouble With Peace", "The Wisdom of Crowds",
                          "A Little Hatred: Book One of The Age of Madness",
                          "The Age of Madness Trilogy"}
        def _is_valid_title(t):
            if not t: return False
            t = t.strip()
            if len(t) > 60 or len(t.split()) > 10: return False
            if t.endswith("…") or t.endswith("."): return False
            if t in INVALID_TITLES: return False
            if GENERIC_RX.match(t): return False
            if _NASLOV_LOS_RX.search(t): return False  # P2.16: naziv fajla, placeholder
            if book_title and book_title.strip().lower() in t.lower(): return False
            if t.lower().startswith(("za ", "posveta", "uvod", "predgovor")): return False
            return True

        if _is_valid_title(toc_naslov):
            return toc_naslov.strip()

        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in ("h1", "h2", "h3"):
                h = s.find(tag)
                if h:
                    t = h.get_text(strip=True)
                    if _is_valid_title(t):
                        return t
            tt = s.find("title")
            if tt:
                t = tt.get_text(strip=True)
                if _is_valid_title(t):
                    return t
            # F0.33: Ne uzimaj prvi pasus kao naslov.
            pass
        except Exception:
            logger.exception("[C1_http] styler.py:1448 Exception")
        return None

    def _classify(hb, href, toc_naslov, book_title, cover_hrefs):
        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in s(["script", "style"]):
                tag.decompose()
            tt = s.find("title")
            title = (tt.get_text(strip=True) if tt else "").lower()
            imgs = len(s.find_all(["img", "svg", "image"]))
            text = s.get_text(" ", strip=True).replace("\ufffc", "")
            tlen = len(text)
            tlow = text[:1200].lower()
            href_base = href.rsplit("/", 1)[-1]

            if tlen < 10 and imgs == 0:
                return False, "prazan", None, False

            if href in cover_hrefs or href_base in cover_hrefs:
                return False, "cover(opf)", None, False
            if title == "cover":
                return False, "cover(title)", None, False
            # FIX 2026-10-26: Calibre "Navigation" stub nije poglavlje
            if title == "navigation":
                return False, "navigation stub", None, False
            if imgs >= 1 and tlen < 30:
                return False, "samo-slika", None, False
            if imgs >= 1 and tlen < 100:
                return False, "cover-slicica", None, False

            if "table of contents" in title or "inhaltsverzeichnis" in title:
                return False, "toc(title)", None, False

            # F0.12: skip frontmatter po h1 tekstu (Calibre stavlja ime knjige u title)
            _h1 = s.find("h1")
            if _h1 is not None:
                _h1_low = _h1.get_text(strip=True).lower()
                _h1_skip = (
                    "navigation",
                    "autor:",
                    "autor :",
                    "o autoru",
                    "sadržaj",
                    "sadrzaj",
                    "table of contents",
                    "naslovna",
                )
                if any(m in _h1_low for m in _h1_skip):
                    return False, "frontmatter(h1)", None, False
            if (
                ("sadrzaj" in tlow or "sadr\u017eaj" in tlow)
                and ("naslovnica" in tlow or "naslovna stranica" in tlow)
                and "autorska prava" in tlow
            ):
                return False, "toc(kombinacija)", None, False

            # F0.10: copyright/marketing filter samo za KRATKE fajlove bez <h1> POGLAVLJE
            _h1 = s.find("h1")
            _has_chapter_h1 = _h1 is not None and "poglavlje" in _h1.get_text(strip=True).lower()
            _je_dugacak = tlen > 5000

            cpy = (
                "\u00a9",
                "copyright",
                "sva prava",
                "all rights",
                "autorska prava",
                "isbn",
                "published by",
                "first published",
                "originally published",
            )
            if not (_has_chapter_h1 or _je_dugacak):
                if any(m in tlow for m in cpy):
                    return False, "copyright", None, False

            mk = (
                "discovery page",
                "about this book",
                "discover more",
                "otkrijte svoje",
                "istra\u017eite darivanja",
                "istra\u017eite svoje",
                "pretpreglede",
                "dodirnite ovdje",
                "tap here",
                "vi\u0161e informacija",
                "saznajte vi\u0161e",
                "preporuke knjiga",
                "noviteti",
            )
            if any(m in title or m in tlow for m in mk):
                return False, "marketing", None, False

            if _je_posveta(tlow, tlen):
                return True, "posveta", None, True

            return True, "ok", _naslov_iz(hb, toc_naslov, book_title), False
        except Exception as e:
            return False, "greska:" + str(e), None, False

    try:
        files = _read(epub_path)
    except Exception as e:
        return {"ok": False, "error": "Citanje: " + str(e)}

    opf_path = next((n for n in files if n.endswith(".opf")), None)
    if not opf_path:
        return {"ok": False, "error": "Nema OPF"}

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    spine = opf_soup.find("spine")
    manifest = opf_soup.find("manifest")
    if not spine or not manifest:
        return {"ok": False, "error": "Nema spine/manifest"}

    opf_dir = str(Path(opf_path).parent)
    if opf_dir == ".":
        opf_dir = ""

    cover_hrefs = set()
    for it in manifest.find_all("item"):
        if "cover-image" in (it.get("properties") or ""):
            cover_hrefs.add(it.get("href", ""))
            cover_hrefs.add(it.get("id", ""))
    for meta in opf_soup.find_all("meta", attrs={"name": "cover"}):
        cid = meta.get("content")
        if cid:
            for it in manifest.find_all("item"):
                if it.get("id") == cid:
                    cover_hrefs.add(it.get("href", ""))
    guide = opf_soup.find("guide")
    if guide:
        for ref in guide.find_all("reference", attrs={"type": "cover"}):
            h = ref.get("href", "").split("#")[0]
            if h:
                cover_hrefs.add(h)

    toc_mapa = _izvuci_toc_mapu(files, opf_dir)
    _log("   -> TOC mapa: %d naslova" % len(toc_mapa), "tech")

    creator, book_title = _meta(files)
    book_uid = "booklyfi"
    dc_lang = "hr"
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                osoup = BeautifulSoup(d, "xml")
                u = osoup.find("dc:identifier")
                if u:
                    book_uid = u.get_text(strip=True)
                lg = osoup.find("dc:language")
                if lg:
                    dc_lang = lg.get_text(strip=True) or "hr"
            except Exception:
                logger.exception("[C1_http] styler.py:1581 Exception")
            break

    for n in list(files.keys()):
        low = n.lower()
        if not low.endswith((".html", ".xhtml", ".htm", ".ncx")):
            continue
        if "booklyfi_" in low:
            continue
        if low.endswith(".ncx"):
            del files[n]
            _log("   -> Obrisan NCX: " + n, "tech")
            continue
        try:
            s = BeautifulSoup(files[n], "html.parser")
            if s.find("nav", attrs={"epub:type": "toc"}):
                del files[n]
                _log("   -> Obrisan NAV TOC: " + n, "tech")
                continue
        except Exception:
            logger.debug("[C3_fallback] styler.py:1601 Exception")
        if any(kw in low for kw in ("toc", "sadrzaj", "contents", "nav.")):
            del files[n]
            _log("   -> Obrisan stari TOC: " + n, "tech")

    id_to_href = {}
    for it in manifest.find_all("item"):
        href = it.get("href", "")
        if href.lower().endswith((".html", ".xhtml", ".htm")):
            id_to_href[it.get("id", "")] = href

    poglavlja = []
    skip_hrefs = set()

    for itemref in spine.find_all("itemref"):
        href = id_to_href.get(itemref.get("idref", ""), "")
        if not href:
            continue
        full = (opf_dir + "/" + href) if opf_dir else href
        hb = files.get(full) or files.get(href)
        if not hb:
            continue
        toc_naslov = toc_mapa.get(href) or toc_mapa.get(full)
        keep, razlog, finalni, no_heading = _classify(
            hb, href, toc_naslov, book_title, cover_hrefs
        )
        if not keep:
            _log("   -> Skip (%s): %s" % (razlog, href), "tech")
            skip_hrefs.add(href)
            skip_hrefs.add(full)
            continue
        poglavlja.append(
            {
                "href": href,
                "full_path": full,
                "order": len(poglavlja) + 1,
                "naslov": finalni,
                "no_heading": no_heading,
            }
        )

    _log("   -> %d poglavlja" % len(poglavlja), "tech")

    for h in skip_hrefs:
        if h in files and not h.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".ttf", ".otf", ".woff")
        ):
            del files[h]
            _log("   -> Obrisan iz EPUB-a: " + h, "tech")

    dropcaps = 0
    # FIX 2026-10-26: PRE obrade HTML-a, spoji .chk u HTML.
    # Time se izbegava da originalni HTML (galley-rw, navodnici)
    # pregazi .chk sadržaj.
    try:
        from epub.packager import _spoji_chk_u_html
        class _TmpEngine:
            pass
        _eng = _TmpEngine()
        _eng.work_dir = Path(STYLED_OUTPUT_DIR).parent / "_tmp_styler_work"
        # Ne koristimo _spoji_chk_u_html jer on radi na engine.work_dir
        # Umesto toga, direktno spojimo .chk u files dict
        import re as _re_s
        from pathlib import Path as _P_s
        from config.settings import CHECKPOINT_BASE_DIR as _CPB_s

        _epub_stem = Path(str(epub_path)).stem
        _epub_stem = _re_s.sub(
            r"^(?:PREVEDENO_)+", "", _epub_stem, flags=_re_s.IGNORECASE
        )
        _epub_stem = _re_s.sub(
            r"(?:_PREVEDENO|_STYLED)+$", "", _epub_stem, flags=_re_s.IGNORECASE
        )
        _svi_sa_chk = [
            _k
            for _k in _CPB_s.glob("_skr_*")
            if (_k / "checkpoints").exists()
            and any((_k / "checkpoints").glob("*.chk"))
        ]
        _exact = _CPB_s / ("_skr_" + _epub_stem)
        _skr = None
        if _exact in _svi_sa_chk:
            _skr = _exact
        else:
            _kandidati = []
            for _k in _svi_sa_chk:
                _k_name = _k.name[len("_skr_") :]
                if _k_name in _epub_stem or _epub_stem in _k_name:
                    _kandidati.append(_k)
                elif (
                    len(_k_name) >= 20
                    and len(_epub_stem) >= 20
                    and (
                        _k_name[:20] == _epub_stem[:20]
                    )
                ):
                    _kandidati.append(_k)
            if len(_kandidati) == 1:
                _skr = _kandidati[0]
            else:
                _skr = None
                _imena = (
                    ", ".join(_k.name for _k in _kandidati)
                    if _kandidati
                    else "(nema)"
                )
                _log(
                    "   -> _skr_ nije jedinstven za "
                    + _epub_stem
                    + " ("
                    + str(len(_kandidati))
                    + ": "
                    + _imena
                    + "), .chk se ne spaja",
                    "warning",
                )

        if _skr:
            _ckpt = _skr / "checkpoints"
            _chk_po_fajlu = {}
            for _f in _ckpt.glob("*.chk"):
                if _f.stem.endswith((".prevod", ".lektura")): continue
                _m = _re_s.match(r"(.+?)_blok_(\d+)$", _f.stem)
                if not _m: continue
                _chk_po_fajlu.setdefault(_m.group(1), {})[int(_m.group(2))] = _f

            def _ocisti_chk(t):
                t = _re_s.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
                if t.strip().startswith("{"):
                    try:
                        import json as _j
                        d = _j.loads(t)
                        for k in ("finalno_polirano", "korektura", "tekst", "translated"):
                            if k in d and isinstance(d[k], str): return d[k]
                    except: pass
                return t

            _spojeno = 0
            for _html_name, _blokovi in _chk_po_fajlu.items():
                if _html_name not in files:
                    # Nađi po basename
                    _found = None
                    for _k2 in files:
                        if _k2.endswith(_html_name) or _html_name.endswith(_k2.split("/")[-1]):
                            _found = _k2; break
                    if not _found: continue
                    _html_name = _found

                try:
                    _soup = BeautifulSoup(files[_html_name].decode("utf-8", "replace"), "html.parser")
                except: continue
                _body = _soup.body
                if not _body: continue

                _ids_all = sorted(_blokovi.keys())
                _delovi = [_ocisti_chk(_blokovi[i].read_text("utf-8", errors="ignore")).strip() for i in _ids_all]
                _blok_ids = [_bi for _bi, _d in zip(_ids_all, _delovi) if _d]
                _delovi = [d for d in _delovi if d]
                if not _delovi: continue

                # F0.7+F0.8: obrisi duplikate (plain vs HTML, HTML vs HTML)
                _za_brisanje = set()
                _parovi = [(i, t) for i, t in enumerate(_delovi)]
                for _i1, _t1 in _parovi:
                    if _i1 in _za_brisanje: continue
                    _je_plain1 = "<p" not in _t1
                    for _i2, _t2 in _parovi:
                        if _i1 >= _i2: continue
                        if _i2 in _za_brisanje: continue
                        _je_plain2 = "<p" not in _t2
                        # plain vs HTML: 70%+ threshold
                        # HTML vs HTML: 90%+ threshold (stroze)
                        if _je_plain1 and _je_plain2:
                            _th = 0.7
                        elif _je_plain1 or _je_plain2:
                            _th = 0.7
                        else:
                            _th = 0.90
                        if not _je_duplikat(_t1, _t2, _th):
                            continue
                        _w1 = len(_t1.split())
                        _w2 = len(_t2.split())
                        # Obrisi kraci
                        if _w1 >= _w2:
                            _dedup_log(epub_path.stem, _html_name, _blok_ids[_i2], _w2, _t2, "dup")
                            _za_brisanje.add(_i2)
                            print(f"  [dup] {_html_name}: obrisan blok_{_i2} ({'plain' if _je_plain2 else 'HTML'}, {_w2}w) — duplikat blok_{_i1} ({_w1}w, {_th*100:.0f}%)")
                        else:
                            _dedup_log(epub_path.stem, _html_name, _blok_ids[_i1], _w1, _t1, "dup")
                            _za_brisanje.add(_i1)
                            print(f"  [dup] {_html_name}: obrisan blok_{_i1} ({'plain' if _je_plain1 else 'HTML'}, {_w1}w) — duplikat blok_{_i2} ({_w2}w, {_th*100:.0f}%)")
                        break
                if _za_brisanje:
                    _delovi = [t for i, t in enumerate(_delovi) if i not in _za_brisanje]
                    _blok_ids = [_bi for i, _bi in enumerate(_blok_ids) if i not in _za_brisanje]
                    if not _delovi: continue

                # F0.6: skrati overlap izmedju susjednih blokova
                _delovi_dedup = [_delovi[0]]
                for _sl, _bid in zip(_delovi[1:], _blok_ids[1:]):
                    # 2026-11-03: fuzzy (cuva <p> strukturu) prije egzaktnog (vraca goli tekst)
                    _sk, _k, _wk = _skrati_overlap_fuzzy(_delovi_dedup[-1], _sl)
                    _n = 0
                    if _k > 0:
                        _dedup_log(epub_path.stem, _html_name, _bid, _wk, _sl, "overlap~")
                        print(f"  [overlap~] {_html_name}: uklonjeno {_k} odlomaka ({_wk} rijeci)")
                    else:
                        _sk, _n = _skrati_overlap(_delovi_dedup[-1], _sl)
                        if _n > 0:
                            _dedup_log(epub_path.stem, _html_name, _bid, _n, _sl, "overlap")
                            print(f"  [overlap] {_html_name}: skraceno {_n} rijeci")
                    if _sk.strip():
                        _delovi_dedup.append(_sk)
                _delovi = _delovi_dedup

                # F0.18b: ako zadnji blok ima >=50 rijeci teksta i zavrsava bez interpunkcije = prekinut
                if _delovi:
                    from bs4 import BeautifulSoup as _BS_f018
                    _zadnji_html = _delovi[-1]
                    _zadnji_tekst = _BS_f018(_zadnji_html, "html.parser").get_text(strip=True)
                    if (
                        _zadnji_tekst
                        and _zadnji_tekst[-1] not in '.!?"\u201c\u201d\u201e\u2014\u2026)\u203a\u00bb:;'
                        and len(_zadnji_tekst.split()) >= 50
                        and not _zavrsava_url_ili_domenom(_zadnji_tekst)
                    ):
                        _delovi[-1] = _zadnji_html + '\n<p>[[NEPREVEDENO: prekinut prevod]]</p>'
                        _log("   -> PREKINUT: " + _html_name + " (" + str(len(_zadnji_tekst.split())) + "w) zavrsava sa " + repr(_zadnji_tekst[-40:]), "warning")

                _body.clear()
                # F0.13b: wrap po bloku PRIJE spajanja (sprecava pogled."Zadovoljstvo)
                _delovi_wrapped = []
                for _t in _delovi:
                    if "<p" in _t.lower():
                        _delovi_wrapped.append(_t)
                    else:
                        _paras = [x.strip() for x in _t.split("\n\n") if x.strip()]
                        _delovi_wrapped.append("".join("<p>" + x + "</p>" for x in _paras))
                _joined = _spoji_blokove(_delovi_wrapped)
                _ns = BeautifulSoup(_joined, "html.parser")
                _src = _ns.body or _ns
                for _c in list(_src.children):
                    _body.append(_c.extract())
                files[_html_name] = str(_soup).encode("utf-8")
                _spojeno += 1
    except Exception as _e:
        print(f"  ⚠ _spoji_chk_u_html greška: {_e}")

    _NASLOV_PREVOD.clear()
    for p in poglavlja:
        soup = BeautifulSoup(
            files[p["full_path"]].decode("utf-8", errors="replace"), "html.parser"
        )
        _ukloni_sve(soup)
        _normalizuj(soup)
        # 2026-11-06: .chk se spaja ovdje direktno (mimo packagera), pa tipografiju
        # (siroci ", crtice, trotocje) primijeni na tekstualnim cvorovima prije provjere
        try:
            from core.tipografija import normaliziraj_soup as _tip_norm
            _apostrof_fix(soup)
            _navodnici_popravi(soup)
            _ukloni_razmak_pred_zatvarajucim(soup)
            _tip_norm(soup)
            _crtica_navodnik_kraj(soup)
        except Exception:
            logger.exception("[tipografija] styler: normalizacija")
        # 2026-11-04: tipografiju radi samo core/tipografija.py (packager); styler samo provjerava
        try:
            from core.tipografija import provjeri as _tip_provjeri
            for _pr in _tip_provjeri(str(soup)):
                logger.warning("[tipografija] %s: %s", p.get("full_path"), _pr)
        except Exception:
            logger.exception("[tipografija] styler: provjera")
        _razdvoji_literalne_nl(soup)
        _popravi_fragment_pocetka(soup)
        _stil_ocisti_p(soup)
        _ukloni_dup_par(soup)
        _ukloni_duplikate_p(soup)
        _dodaj_vijenac(soup)
        _ocisti_fffc(soup)
        if p.get("no_heading"):
            pass
        else:
            _h1_tekst = _dodaj_naslov(
                soup, p["order"], naslov=p.get("naslov"), knjiga=book_title
            )
            # P2.16: nav/ncx moraju imati isti naslov kao h1 u fajlu
            if _h1_tekst:
                p["naslov"] = _h1_tekst
        p["_ima_h1"] = bool(soup.find("h1"))
        if _dodaj_dropcap(soup):
            dropcaps += 1
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            parent = soup.html if soup.html else soup
            parent.insert(0, head)
        st = soup.new_tag("style", type="text/css")
        st.string = CSS
        head.append(st)
        files[p["full_path"]] = str(soup).encode("utf-8")

    _log("   -> %d dropcapa" % dropcaps, "tech")

    nas_path = (
        (opf_dir + "/booklyfi_001_naslovna.xhtml")
        if opf_dir
        else "booklyfi_001_naslovna.xhtml"
    )
    imp_path = (
        (opf_dir + "/booklyfi_002_impresum.xhtml")
        if opf_dir
        else "booklyfi_002_impresum.xhtml"
    )
    year = _dt.datetime.now().year
    nas_body = (
        '<div style="text-align:center;padding:3em 5% 0;">'
        '<p style="font-size:0.85em;letter-spacing:0.3em;color:#8B6914;">BOOKLYFI IZDANJE</p>'
        '<hr/><h1 style="font-size:2.4em;">' + _esc(book_title) + "</h1>"
        '<hr/><p style="font-size:1.3em;margin-top:3em;">' + _esc(creator) + "</p>"
        '<p style="font-size:0.9em;color:#8B6914;margin-top:5em;">Booklyfi &#183; '
        + str(year)
        + "</p></div>"
    )
    imp_body = (
        '<h1 style="text-align:center;">IMPRESUM</h1>'
        "<p><b>Naslov:</b> " + _esc(book_title) + "</p>"
        "<p><b>Autor:</b> " + _esc(creator) + "</p>"
        "<p><b>ID:</b> " + _esc(book_uid) + "</p>"
        "<p><b>Izdanje:</b> Booklyfi digitalno izdanje, " + str(year) + ".</p>"
        "<p><b>Format:</b> EPUB</p><p>Sva prava zadrzana.</p>"
    )
    files[nas_path] = _page("Naslovna", nas_body).encode("utf-8")
    files[imp_path] = _page("Impresum", imp_body).encode("utf-8")

    ncx_path = (opf_dir + "/toc.ncx") if opf_dir else "toc.ncx"
    _ncx_uid = book_uid
    try:
        _ps = BeautifulSoup(files[opf_path], "xml")
        _pk = _ps.find("package")
        _uid_id = _pk.get("unique-identifier") if _pk else None
        for _di in _ps.find_all("dc:identifier"):
            if _uid_id and _di.get("id") == _uid_id and _di.get_text(strip=True):
                _ncx_uid = _di.get_text(strip=True)
                break
    except Exception:
        pass
    nps = []
    _po = 0
    for p in poglavlja:
        if not p.get("_ima_h1"):
            continue  # nema h1 u EPUB-u -> nema u TOC-u
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        _po += 1
        nps.append(
            '<navPoint id="np-%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>'
            % (p["order"], _po, _esc(nas), _esc(p["href"]))
        )
    files[ncx_path] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        '<head><meta name="dtb:uid" content="' + _esc(_ncx_uid) + '"/>'
        '<meta name="dtb:depth" content="1"/></head>'
        "<docTitle><text>" + _esc(book_title) + "</text></docTitle>"
        "<navMap>" + "".join(nps) + "</navMap></ncx>"
    ).encode("utf-8")

    try:
        _pkg = BeautifulSoup(files[opf_path], "xml").find("package")
        _ver = _pkg.get("version", "2.0") if _pkg is not None else "2.0"
    except Exception:
        _ver = "2.0"
    _epub2 = str(_ver).startswith("2")  # EPUB 2 paket: nav.xhtml i dcterms:modified nisu dopusteni
    nav_path = (opf_dir + "/nav.xhtml") if opf_dir else "nav.xhtml"
    nav_its = []
    for p in poglavlja:
        if not p.get("_ima_h1"):
            continue  # nema h1 u EPUB-u -> nema u TOC-u
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        nav_its.append('<li><a href="%s">%s</a></li>' % (_esc(p["href"]), _esc(nas)))
    first_href = poglavlja[0]["href"] if poglavlja else Path(nas_path).name
    nav_body = (
        '<nav epub:type="toc" id="toc"><h1>Sadržaj</h1><ol>'
        + "".join(nav_its)
        + "</ol></nav>"
        '<nav epub:type="landmarks" hidden="hidden"><h2>Orijentiri</h2><ol>'
        '<li><a epub:type="titlepage" href="'
        + _esc(Path(nas_path).name)
        + '">Naslovna</a></li>'
        '<li><a epub:type="copyright-page" href="'
        + _esc(Path(imp_path).name)
        + '">Impresum</a></li>'
        '<li><a epub:type="bodymatter" href="' + _esc(first_href) + '">Početak</a></li>'
        "</ol></nav>"
    )
    files[nav_path] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<!DOCTYPE html>"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'lang="' + _esc(dc_lang) + '">'
        '<head><meta charset="utf-8"/><title>Sadržaj</title></head>'
        "<body>" + nav_body + "</body></html>"
    ).encode("utf-8")
    if _epub2:
        files.pop(nav_path, None)

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    mtag = opf_soup.find("manifest")
    stag = opf_soup.find("spine")
    existing = set(files.keys())

    for it in list(mtag.find_all("item")):
        href = it.get("href", "")
        fh = (opf_dir + "/" + href) if opf_dir else href
        if fh not in existing and href not in existing:
            it.decompose()

    for _f in sorted(existing):
        if not _f.lower().endswith(".css"):
            continue
        _h = _f[len(opf_dir) + 1:] if opf_dir and _f.startswith(opf_dir + "/") else _f
        if any(_i.get("href") == _h for _i in mtag.find_all("item")):
            continue
        _ids = {_i.get("id") for _i in mtag.find_all("item")}
        _n = 1
        while "booklyfi-css-%d" % _n in _ids:
            _n += 1
        mtag.append(
            opf_soup.new_tag(
                "item",
                attrs={"id": "booklyfi-css-%d" % _n, "href": _h, "media-type": "text/css"},
            )
        )
    gd = opf_soup.find("guide")
    if gd:
        for ref in list(gd.find_all("reference")):
            h = ref.get("href", "").split("#")[0]
            fh = (opf_dir + "/" + h) if opf_dir else h
            if fh not in existing and h not in existing:
                ref.decompose()

    for iid, path, mt in (
        ("booklyfi-naslovna", nas_path, "application/xhtml+xml"),
        ("booklyfi-impresum", imp_path, "application/xhtml+xml"),
        ("ncx", ncx_path, "application/x-dtbncx+xml"),
    ):
        for old in mtag.find_all("item", id=iid):
            old.decompose()
        ni = opf_soup.new_tag("item")
        ni["id"] = iid
        ni["href"] = Path(path).name
        ni["media-type"] = mt
        mtag.append(ni)
    for old in mtag.find_all("item", id="nav"):
        old.decompose()
    if not _epub2:
        ni = opf_soup.new_tag("item")
        ni["id"] = "nav"
        ni["href"] = Path(nav_path).name
        ni["media-type"] = "application/xhtml+xml"
        ni["properties"] = "nav"
        mtag.append(ni)

    if not _epub2 and not opf_soup.find("meta", attrs={"property": "dcterms:modified"}):
        now = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = opf_soup.new_tag("meta")
        meta["property"] = "dcterms:modified"
        meta.string = now
        md = opf_soup.find("metadata")
        if md:
            md.append(meta)

    kept_hrefs = {p["href"] for p in poglavlja}
    orig_ids = []
    for ir in stag.find_all("itemref"):
        iid = ir.get("idref", "")
        href = id_to_href.get(iid, "")
        if href and href in kept_hrefs:
            orig_ids.append(iid)

    for ir in stag.find_all("itemref"):
        ir.decompose()
    # 2026-10-24 B7: dedup base64 slike u zajednicke PNG pre OPF build
#     _shared_images = _ekstrahuj_zajednicke_slike(files)
    _shared_images = []  # FIX F0.1: funkcija obrisana, dedup onemogucen (inline base64)
    if _shared_images:
        _log("   -> %d zajednickih slika (dedup base64)" % len(_shared_images), "tech")

    # 2026-10-24 B7: dodaj manifest items za zajednicke slike
    if _shared_images:
        for _png_path in _shared_images:
            _ext = _png_path.rsplit(".", 1)[-1].lower()
            _hash_part = (
                _png_path.rsplit("/", 1)[-1]
                .replace("booklyfi-shared-", "")
                .rsplit(".", 1)[0]
            )
            ni = opf_soup.new_tag("item")
            ni["id"] = "booklyfi-shared-" + _hash_part
            ni["href"] = _png_path
            ni["media-type"] = "image/jpeg" if _ext in ("jpg", "jpeg") else "image/png"
            mtag.append(ni)

    for iid in (
        ("booklyfi-naslovna", "booklyfi-impresum")
        if _epub2
        else ("booklyfi-naslovna", "booklyfi-impresum", "nav")
    ):
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    for iid in orig_ids:
        if iid in ("booklyfi-naslovna", "booklyfi-impresum", "nav", "ncx"):
            continue
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    if not stag.get("toc"):
        stag["toc"] = "ncx"
    files[opf_path] = str(opf_soup).encode("utf-8")


    if output_path:
        out = Path(output_path)
    else:
        od = Path(STYLED_OUTPUT_DIR)
        od.mkdir(parents=True, exist_ok=True)
        out = od / _ime(creator, book_title)
    _img_popravi(files)
    _write(out, files)

    return {
        "ok": True,
        "epub_path": str(out),
        "chapters": len(poglavlja),
        "dropcaps_added": dropcaps,
        "toc_created": True,
        "error": None,
    }

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Upotreba: python -m epub.styler <knjiga.epub> [izlaz.epub]")
        sys.exit(1)
    res = run_epub_styler(
        sys.argv[1],
        output_path=sys.argv[2] if len(sys.argv) > 2 else None,
        log_callback=lambda m, t="info": print(f"  {m}"),
    )
    print(f"\n{'✅ OK' if res['ok'] else '❌ ' + str(res['error'])}")
    if res["ok"]:
        print(f"   EPUB:      {res['epub_path']}")
        print(f"   Poglavlja: {res['chapters']}")
        print(f"   Dropcaps:  {res['dropcaps_added']}")


