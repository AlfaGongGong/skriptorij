

# epub/parser.py
import re

import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from bs4 import BeautifulSoup, NavigableString

# Regex: JSON wrapper artifacts like {"finalno_polirano": "..." or partial forms.
# Tipografski navodnici „"'' (koje AI modeli ponekad koriste umjesto ASCII ") su
# uključeni u klasu znakova kako bi čišćenje radilo i na tim varijantama.
#
# _Q = klasa znakova koja obuhvata i ASCII " i sve tipografske navodnike i whitespace
_Q = r'[\u201e\u201c\u201d\u2018\u2019\u201a\u201b"\s]'
# _Q1 = samo navodnici (bez whitespace) za graničnike vrijednosti
_Q1 = r'[\u201e\u201c\u201d\u2018\u2019\u201a\u201b"]'
# Ključevi JSON omotača koje prepoznajemo
_JSON_KEYS = r'(?:finalno_polirano|korektura|tekst|prijevod)'

_JSON_ARTIFACT_PREFIX = re.compile(
    rf'^\s*\{{{_Q}*{_JSON_KEYS}{_Q}*:\s*{_Q}*',
    re.IGNORECASE,
)
_JSON_ARTIFACT_TRAILER = re.compile(
    r'[\u201e\u201c\u201d\u2018\u2019\u201a\u201b"\s]*\}\s*$'
)

# Regex za ugniježđeni JSON u sredini tekst-čvora:
# hvata slučajeve gdje AI upiše dio teksta pa doda JSON wrapper na kraju, npr.:
#   "Uputi dramatične{ „korektura": „...cijeli tekst..."}"
# Pohlepni (.+?) je namjerno kratak (non-greedy) jer tražimo do prve zatvorene tipografske/ASCII ".
_EMBEDDED_JSON_RE = re.compile(
    rf'\{{{_Q}*(?:finalno_polirano|korektura){_Q}*:\s*{_Q1}(.*?){_Q1}\s*\}}\s*$',
    re.IGNORECASE | re.DOTALL,
)


def _ocisti_epub_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(True):
            for node in list(tag.children):
                if isinstance(node, NavigableString):
                    cleaned = re.sub(r"^[\n\r\t\v]+", "", str(node))
                    if cleaned != str(node):
                        node.replace_with(NavigableString(cleaned))
        return str(soup)
    except Exception:
        return html


def _strip_json_artifacts_from_html(html_fajlovi: list, log_fn=None) -> int:
    """
    Uklanja JSON omotače poput {"finalno_polirano": "..." koji su procurili
    u HTML tekst tokom AI obrade. Radi direktno nad tekst-čvorovima BeautifulSoup-a.
    Podržava i tipografske navodnike „"'' koje AI modeli ponekad koriste umjesto ASCII ".
    Podržava i ugniježđeni JSON — gdje JSON nije na početku tekst-čvora nego u sredini/kraju.
    """
    fixed = 0
    for fajl in html_fajlovi:
        try:
            original = fajl.read_text("utf-8", errors="replace")
            # Brza provjera — skipuj fajlove bez artefakta
            if "finalno_polirano" not in original and "korektura" not in original:
                continue
            soup = BeautifulSoup(original, "html.parser")
            changed = False
            for node in soup.find_all(string=True):
                txt = str(node)
                if "finalno_polirano" not in txt and "korektura" not in txt:
                    continue
                if txt.strip().startswith("{"):
                    # Slučaj 1: JSON wrapper je na početku čvora (normalni artefakt)
                    cleaned = _JSON_ARTIFACT_PREFIX.sub("", txt)
                    # Ukloni ostatak JSON zatvarača samo s kraja
                    cleaned = _JSON_ARTIFACT_TRAILER.sub("", cleaned)
                    if cleaned != txt:
                        node.replace_with(NavigableString(cleaned))
                        changed = True
                else:
                    # Slučaj 2: JSON wrapper je ugniježđen u sredini/kraju teksta.
                    # Primjer: "Uputi dramatične{ „korektura": „...cijeli tekst..."}"
                    # Izvuci vrijednost iz JSON-a i zamijeni cijeli čvor s njom.
                    m = _EMBEDDED_JSON_RE.search(txt)
                    if m:
                        extracted = m.group(1).strip()
                        if extracted and extracted != txt:
                            node.replace_with(NavigableString(extracted))
                            changed = True
            if changed:
                fajl.write_text(str(soup), encoding="utf-8")
                fixed += 1
        except Exception:
            pass
    if fixed and log_fn:
        log_fn(f"🔧 JSON omotači uklonjeni iz {fixed} HTML fajl(ov)a.", "tech")
    return fixed

def _ukloni_inline_stilove(html_fajlovi: list, log_fn=None) -> int:
    modificirano = 0
    for fajl in html_fajlovi:
        try:
            original = fajl.read_text("utf-8", errors="ignore")
            if "style=" not in original: continue
            soup = BeautifulSoup(original, "html.parser")
            izmijenjeno = False
            for tag in soup.find_all(True):
                if tag.get("style"):
                    del tag["style"]
                    izmijenjeno = True
            if izmijenjeno:
                fajl.write_text(str(soup), encoding="utf-8")
                modificirano += 1
        except Exception: pass
    if modificirano and log_fn:
        log_fn(f"🎨 Inline stilovi očišćeni u {modificirano} HTML fajl(ov)a.", "tech")
    return modificirano

def _zamijeni_epub_css(html_fajlovi: list, work_dir, log_fn=None) -> int:
    # pojednostavljeno
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# EpubParser — čita EPUB zip i vraća poglavlja za preview
# ─────────────────────────────────────────────────────────────────────────────
import zipfile

def _booklyfi_charset_filter(tekst: str) -> str:
    """
    Uklanja izolirane ćirilične znakove iz latiničnog teksta.
    AI modeli (posebno Groq/Cerebras) ponekad vrate jedno ćirilično
    slovo usred latiničnog teksta (npr. nepokolебljivo).
    Radi samo kad je ćirilica manjina (<10% znakova).
    """
    if not tekst:
        return tekst
    cir = sum(1 for c in tekst if '\u0400' <= c <= '\u04FF')
    ukupno = max(len(tekst), 1)
    if cir == 0 or cir / ukupno > 0.10:
        return tekst  # ili čisto latinica ili stvarno ćirilični tekst
    # Zamijeni svaki ćirilični znak odgovarajućim latiničnim, ako postoji
    _CIR_LAT = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ж':'ž',
        'з':'z','и':'i','ј':'j','к':'k','л':'l','м':'m','н':'n',
        'о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
        'х':'h','ц':'c','ч':'č','ш':'š','ђ':'đ','ћ':'ć','њ':'nj',
        'љ':'lj','џ':'dž','А':'A','Б':'B','В':'V','Г':'G','Д':'D',
        'Е':'E','Ж':'Ž','З':'Z','И':'I','Ј':'J','К':'K','Л':'L',
        'М':'M','Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T',
        'У':'U','Ф':'F','Х':'H','Ц':'C','Ч':'Č','Ш':'Š','Ђ':'Đ',
        'Ћ':'Ć','Њ':'Nj','Љ':'Lj','Џ':'Dž',
    }
    return ''.join(_CIR_LAT.get(c, c) for c in tekst)


def _booklyfi_deduplicate_heading(tekst: str) -> str:
    """
    Uklanja duplikate naslova poglavlja.
    Primjer: "POGLAVLJE 3 POGLAVLJE 3" → "POGLAVLJE 3"
    Nastaje kad packager/chunker upiše heading i tekst koji počinje
    headingom zajedno.
    """
    if not tekst:
        return tekst
    # Pokreni samo ako vidimo potencijalnu duplikaciju (performance)
    if tekst.count('\n') > 2:
        return tekst  # preskači duge blokove
    # Pronađi ponavljanje na početku: "X X" gdje X > 5 znakova
    import re as _re
    pattern = _re.compile(
        r'^((?:[A-ZČĆŠŽĐ][A-ZČĆŠŽĐA-Za-z0-9\s]+){1,8})\s+\1',
        _re.MULTILINE | _re.UNICODE
    )
    return pattern.sub(r'\1', tekst)




class EpubParser:
    """
    Minimalni EPUB parser za live preview.
    Čita spine redoslijed iz OPF-a, parsira svaki HTML dokument
    i vraća listu poglavlja s naslovom, HTML sadržajem i plain textom.
    """

    def __init__(self, epub_path: str):
        self.epub_path = str(epub_path)
        self._chapters = None

    # ── Javni API ─────────────────────────────────────────────────────────────

    def get_chapters(self) -> list:
        """
        Vraća listu dict-ova:
          { title, html, text, partial, idx }
        """
        if self._chapters is not None:
            return self._chapters
        try:
            self._chapters = self._parse()
        except Exception:
            self._chapters = []
        return self._chapters

    # ── Interni parseri ───────────────────────────────────────────────────────

    def _parse(self) -> list:
        chapters = []
        with zipfile.ZipFile(self.epub_path, "r") as zf:
            names = zf.namelist()

            # 1. Pronađi OPF (content.opf ili META-INF/container.xml → rootfile)
            opf_path = self._find_opf(zf, names)

            if opf_path:
                spine_items = self._parse_opf_spine(zf, opf_path)
            else:
                # Fallback: uzmi sve HTML fajlove abecednim redom
                spine_items = sorted(
                    n for n in names
                    if n.lower().endswith((".html", ".xhtml", ".htm"))
                    and not n.startswith("__")
                )

            opf_dir = "/".join(opf_path.split("/")[:-1]) if opf_path else ""

            for idx, item_href in enumerate(spine_items):
                # Normaliziraj putanju unutar zipa
                full_path = (opf_dir + "/" + item_href).lstrip("/") if opf_dir else item_href

                # Provjeri alternativu ako puna putanja ne postoji
                if full_path not in names:
                    # Pokušaj direktno
                    if item_href in names:
                        full_path = item_href
                    else:
                        continue

                try:
                    raw = zf.read(full_path).decode("utf-8", errors="replace")
                except Exception:
                    continue

                title, html_body, plain = self._extract_content(raw, idx)
                if not plain.strip():
                    continue  # Preskoči prazna poglavlja

                chapters.append({
                    "idx":     idx,
                    "title":   title,
                    "html":    html_body,
                    "text":    plain[:500],   # Kratki preview teksta
                    "partial": False,
                })

        return chapters

    def _find_opf(self, zf, names) -> str:
        """Pronađi putanju do OPF fajla."""
        # Direktno
        for n in names:
            if n.endswith(".opf"):
                return n
        # Preko container.xml
        if "META-INF/container.xml" in names:
            try:
                container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
                soup = BeautifulSoup(container_xml, "html.parser")
                rf = soup.find("rootfile")
                if rf and rf.get("full-path"):
                    return rf["full-path"]
            except Exception:
                pass
        return ""

    def _parse_opf_spine(self, zf, opf_path: str) -> list:
        """Parsira OPF i vraća href-ove po spine redoslijedu."""
        try:
            opf_raw = zf.read(opf_path).decode("utf-8", errors="replace")
            soup = BeautifulSoup(opf_raw, "html.parser")

            # Manifest: id → href
            manifest = {}
            for item in soup.find_all("item"):
                item_id   = item.get("id", "")
                item_href = item.get("href", "")
                media     = item.get("media-type", "")
                if "html" in media or item_href.endswith((".html", ".xhtml", ".htm")):
                    manifest[item_id] = item_href

            # Spine: idref redoslijed
            spine_hrefs = []
            for itemref in soup.find_all("itemref"):
                idref = itemref.get("idref", "")
                if idref in manifest:
                    spine_hrefs.append(manifest[idref])

            return spine_hrefs if spine_hrefs else list(manifest.values())
        except Exception:
            return []

    def _extract_content(self, raw_html: str, idx: int):
        """Vraća (title, body_html, plain_text) iz HTML stringa."""
        try:
            soup = BeautifulSoup(raw_html, "html.parser")

            # Naslov: <title>, h1, h2 — kojegod nađe
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)
            if not title:
                for htag in ("h1", "h2", "h3"):
                    h = soup.find(htag)
                    if h:
                        title = h.get_text(strip=True)
                        break
            if not title:
                title = f"Poglavlje {idx + 1}"

            # Body HTML — samo sadržaj <body> taga
            body = soup.find("body")
            body_html = str(body) if body else str(soup)

            # Plain text (za provjeru je li prazan)
            plain = soup.get_text(separator=" ", strip=True)

            return title, body_html, plain

        except Exception:
            return f"Poglavlje {idx + 1}", raw_html, raw_html[:200]
