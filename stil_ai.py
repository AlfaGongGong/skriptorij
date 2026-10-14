#!/usr/bin/env python3
"""
stil_ai.py — Stilizacija EPUB-a s AI normalizacijom dijaloga.

Koristenje:
    python3 stil_ai.py <knjiga.epub> [--bez-ai]
    python3 stil_ai.py --ornamenti        (samo provjeri ornamente/dropcap, ne dira EPUB)

--bez-ai : ne zove AI (naslovi iz teksta, scena "description",
           dijalog samo heuristikom: odlomak koji pocinje crticom/navodnicima).
"""
import sys, os, re, json, time, base64, shutil, tempfile, zipfile, posixpath, struct
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

SKRIPTORIJ_DIR = "/root/skriptorij"
sys.path.insert(0, SKRIPTORIJ_DIR)
for _d in Path(SKRIPTORIJ_DIR).rglob("__pycache__"):
    shutil.rmtree(_d, ignore_errors=True)

import warnings
from bs4 import BeautifulSoup, NavigableString
try:
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    pass

ORNAMENTS_DIR = os.environ.get(
    "STIL_ORNAMENTS", "/storage/emulated/0/Books/MoonReader/ornaments_small_size")

# ═══ Stilovi ═══
STYLE_BODY = ("font-family:Georgia,serif;font-size:1em;line-height:1.6;"
              "margin:0 5%;position:relative;")
STYLE_P = ("margin:0;padding:0;text-indent:1.8em;"
           "font-size:1em;line-height:1.6;")
STYLE_P_FIRST = ("margin:0.3em 0 0 0;padding:0;"
                 "text-indent:0;font-size:1em;line-height:1.6;")
STYLE_DIALOG = ("margin:0.3em 0;padding:0 0 0 1.5em;"
                "text-indent:-1em;font-size:1em;line-height:1.6;")
STYLE_BREAK = ("text-align:center;text-indent:0;margin:1em 0;padding:0;"
               "letter-spacing:0.4em;color:#8B0000;")
STYLE_H1 = ("font-family:Georgia,serif;color:#8B0000;text-align:center;"
            "font-size:1.8em;font-weight:600;letter-spacing:0.05em;"
            "margin:0.5em 0 0.8em 0;line-height:1.3;text-indent:0;")
STYLE_H2 = ("font-family:Georgia,serif;color:#8B0000;text-align:center;"
            "font-size:1.2em;font-weight:600;"
            "margin:1em 0 0.6em 0;line-height:1.3;text-indent:0;")
STYLE_ORN = "text-align:center;margin:0.5em auto 0.8em auto;padding:0;text-indent:0;"
STYLE_DC_IMG = ("float:left;display:inline;"
                "width:2.5em;height:auto;max-width:none;"
                "margin:0.05em 0.15em 0 0;padding:0;vertical-align:top;"
                "shape-outside:margin-box;")
STYLE_ORN_IMG = "display:inline-block;height:2.5em;width:auto;"

# ═══ CSS BLOK — ubacuje se u <style> tag u svako poglavlje ═══
CSS_BLOCK = """body{font-family:Georgia,serif;font-size:1em;line-height:1.6;margin:0 5%;position:relative;}"""


def _soup_new_tag(soup, name, text):
    from bs4 import Tag
    t = soup.new_tag(name)
    t.string = text
    return t



CLS_DIJALOG = "booklyfi-dijalog"
CLS_NASLOV = "booklyfi-naslov"
CLS_PRVI = "booklyfi-prvi"
CLS_DC_BLOCK = "booklyfi-dropcap-block"
CLS_DC_IMG = "booklyfi-dropcap"

# ═══ Dropcap / ornamenti ═══
DROPCAP_MAP = {}
ORN_INDEX = {}      # naziv fajla (lower-case) -> Path, svi fajlovi u folderu
DIGRAFI = ("LJ", "NJ", "DŽ")
RES_SUBDIR = "images/booklyfi"      # gdje u EPUB-u (relativno na OPF) idu slike
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


@lru_cache(maxsize=None)
def _mime(path):
    """Stvarni tip slike po sadrzaju (a ne po nastavku); None ako nije slika."""
    try:
        h = Path(path).read_bytes()[:12]
    except OSError:
        return None
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if h.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if h.startswith(b"GIF8"):
        return "image/gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    return None


@lru_cache(maxsize=None)
def _b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def ucitaj_dropcap():
    DROPCAP_MAP.clear()
    ORN_INDEX.clear()
    d = Path(ORNAMENTS_DIR)
    if not d.exists():
        print(f"UPOZORENJE: folder s ornamentima ne postoji: {d}")
        return
    for f in sorted(d.iterdir()):
        ORN_INDEX.setdefault(f.name.lower(), f)
        if f.suffix.lower() == ".png" and len(f.stem) in (1, 2) and f.stem.isalpha():
            if _mime(str(f)):
                DROPCAP_MAP.setdefault(f.stem.upper(), f)
            else:
                print(f"UPOZORENJE: {f.name} nije ispravna slika, preskacem")


def _ime_ornamenta(scena):
    return "center_ornament.png" if scena == "center" else f"ornament_{scena}.png"


def _opis_slike(path):
    """Npr. 'PNG 800x200 RGBA 8-bit 310KB' (stvarni format iz sadrzaja, ne iz nastavka)."""
    p = Path(path)
    kb = p.stat().st_size / 1024
    mime = _mime(str(p))
    if mime is None:
        return f"NIJE SLIKA ({kb:.0f}KB)"
    if mime == "image/png":
        h = p.read_bytes()[:33]
        if len(h) < 29:
            return f"PNG OSTECEN/prekratak ({kb:.0f}KB)"
        w, hh = struct.unpack(">II", h[16:24])
        tip = {0: "gray", 2: "RGB", 3: "palette", 4: "gray+A", 6: "RGBA"}.get(h[25], str(h[25]))
        return f"PNG {w}x{hh} {tip} {h[24]}-bit{' interlaced' if h[28] else ''} {kb:.0f}KB"
    return f"{mime.split('/')[1].upper()} {kb:.0f}KB"


def provjeri_ornamente():
    """Ispisi sto od ornamenata stvarno postoji i kakvi su (nema fajla -> nema ornamenta, tiho)."""
    print("Ornamenti:")
    for sc in SCENE + ("center",):
        f = ORN_INDEX.get(_ime_ornamenta(sc))
        print(f"   {sc:12s} " + ("✗ nema fajla" if f is None else _opis_slike(f)))
    if DROPCAP_MAP:
        kljuc = sorted(DROPCAP_MAP)[0]
        print(f"   dropcap {kljuc}:".ljust(16) + _opis_slike(DROPCAP_MAP[kljuc]))
    if any(f is None for f in (ORN_INDEX.get(_ime_ornamenta(sc)) for sc in SCENE + ("center",))):
        ostalo = [f.name for f in ORN_INDEX.values() if len(f.stem) > 2][:15]
        print("   Ostali fajlovi u folderu: " + (", ".join(ostalo) or "(nema)"))


def _nadji_ornament(scena):
    for ime in (_ime_ornamenta(scena), _ime_ornamenta("center")):
        f = ORN_INDEX.get(ime)
        if f is not None and _mime(str(f)):
            return f
    return None


# ═══ AI (fleet) ═══
_AI = {"fleet": None, "prio": None, "api_call": None}
_PADOVI = {}   # provider -> uzastopni neuspjesi
_BLOK = {}     # provider -> do kad je preskacemo


def init_fleet():
    try:
        from api_fleet import FleetManager
        from config.settings import CONFIG_PATH
        from config.ai_config import PROVIDER_PRIORITY
        from network.http_client import api_call
        fleet = FleetManager(config_path=CONFIG_PATH)
    except Exception as e:
        print(f"Fleet GRESKA: {e}")
        return False
    _AI.update(fleet=fleet, prio=PROVIDER_PRIORITY, api_call=api_call)
    print(f"Fleet: {len([k for k, v in fleet.fleet.items() if v])} providera")
    return True


def _pad(provider):
    n = _PADOVI[provider] = _PADOVI.get(provider, 0) + 1
    if n >= 3:  # 3 uzastopna neuspjeha -> pauza 2 min (umjesto 3x180s timeouta po pozivu)
        _BLOK[provider] = time.time() + 120
        _PADOVI[provider] = 0


def ai_call(prompt, system, max_tokens=4000, timeout=180):
    fleet = _AI["fleet"]
    if fleet is None:
        return None
    for provider in _AI["prio"].get("ANALIZA", ["GEMINI"]):
        if _BLOK.get(provider, 0) > time.time():
            continue
        key = fleet.get_best_key(provider)
        if not key:
            continue
        model = fleet.get_active_model(provider)
        if not model:
            continue
        try:
            r = _AI["api_call"](provider=provider, model=model, api_key=key,
                                system=system, user=prompt,
                                temperature=0.1, max_tokens=max_tokens, timeout=timeout)
        except Exception as e:
            print(f"      AI {provider}: {type(e).__name__}: {str(e)[:80]}")
            _pad(provider)
            continue
        if r:
            _PADOVI[provider] = 0
            return r
        _pad(provider)
    return None


def _spasi_objekte(text):
    """Iz odsjecenog JSON arraya izvuci sve kompletne objekte."""
    dec = json.JSONDecoder()
    out = []
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out or None


def parse_json(text):
    if not text:
        return None
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", text, re.S)
    if m:
        text = m.group(1).strip()
    dec = json.JSONDecoder()
    if text.startswith("["):
        try:
            return dec.raw_decode(text)[0]
        except ValueError:
            return _spasi_objekte(text)  # odgovor odsjecen (max_tokens)
    for m in re.finditer(r"[\[{]", text):
        try:
            return dec.raw_decode(text[m.start():])[0]
        except ValueError:
            continue
    return _spasi_objekte(text)


def _kao_listu(data):
    """AI ponekad vrati {"rezultat": [...]} ili jedan objekt umjesto arraya."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]
    return []


# ═══ Tekstni helperi ═══
_PH_LO, _PH_HI = "\ue000", "\uf8ff"   # privatni znakovi = zamjene za HTML tagove
_TAG_RE = re.compile(r"<[^>]*>")


def _mask(html):
    """Zamijeni HTML tagove privatnim znakovima da <i>/<em>/<a> prezive obradu teksta."""
    tags = []

    def rep(m):
        tags.append(m.group(0))
        return chr(0xE000 + len(tags) - 1)
    return _TAG_RE.sub(rep, html), tags


def _unmask(s, tags):
    return "".join(tags[ord(c) - 0xE000] if _PH_LO <= c <= _PH_HI else c for c in s)


def _prvo_slovo(t):
    return next((c for c in t if c.isalpha()), "")


def _malo(t):
    return _prvo_slovo(t).islower()


def _veliko(t):
    return _prvo_slovo(t).isupper()


def _klase(el):
    c = el.get("class")
    if isinstance(c, str):
        return c.split()
    return list(c or [])


def _je_prekid(t):
    """Odlomak tipa '* * *', '###', '~~~' (prekid scene)."""
    return (len(t) <= 15 and not any(c.isalnum() for c in t)
            and re.search(r"[*#~•·◆♦✦]", t) is not None)


# ═══ Dijalog: prepoznavanje i pretvorba u crticu ═══
_POCINJE_DIJ = re.compile(r"^\s*[-–—―„»«“\"]")
_KAND = re.compile(r"[„»«“\"]|\s[–—―]\s")
_DASH_START = re.compile(r"^[\s\ue000-\uf8ff]*[-–—―]+\s*")
_INT_DASH = re.compile(r"\s+[–—―]+\s+")
_NAV_OTV = {"„": "“”\"", "»": "«", "«": "»", "\"": "\"”", "“": "”\""}


def _pocinje_dijalogom(t):
    return _POCINJE_DIJ.match(t) is not None


def _je_kandidat(t):
    return _pocinje_dijalogom(t) or _KAND.search(t) is not None


def _segmentiraj_navodnike(t):
    """[(kind, text)] kind: 'g' = govor (u navodnicima), 'n' = pripovijedanje."""
    segs, buf, zatv = [], [], None

    def flush(kind):
        s = "".join(buf).strip()
        buf.clear()
        if s:
            segs.append((kind, s))

    for i, ch in enumerate(t):
        if zatv is None:
            # “ je otvarajuci samo ako se kasnije pojavi ” (inace je BCS zatvarajuci)
            if ch in _NAV_OTV and not (ch == "“" and "”" not in t[i + 1:]):
                flush("n")
                zatv = _NAV_OTV[ch]
            else:
                buf.append(ch)
        elif ch in zatv:
            flush("g")
            zatv = None
        else:
            buf.append(ch)
    flush("g" if zatv is not None else "n")
    return segs


def _gradi_navodnici(t, razdvoji):
    """
    „Dosta!“ rekao je. „Idemo.“  ->  — Dosta! — rekao je. — Idemo.
    Pripovijedanje koje ne izgleda kao oznaka govornika ide u zaseban odlomak.
    razdvoji=True (AI: >=2 govornika) -> svaki novi govor je novi odlomak.
    """
    segs = _segmentiraj_navodnike(t)
    if not any(k == "g" for k, _ in segs):
        return None
    out, cur, prev, pending = [], None, None, ""
    for kind, s in segs:
        if kind == "g":
            if cur is not None and not razdvoji:
                cur += " — " + s
            else:
                if cur is not None:
                    out.append(("d", cur))
                cur = pending + "— " + s
                pending = ""
            prev = "g"
            continue
        if not any(c.isalnum() for c in s):     # samo interpunkcija / tagovi
            if cur is not None:
                cur += s
            else:
                pending += s
            continue
        zarez = s[0] in ",;"
        crtica = s[0] in "-–—―"
        s = re.sub(r"^[,;\-–—―\s]+", "", s)
        if cur is not None and prev == "g" and (zarez or crtica or _malo(s)):
            if zarez and not re.search(r"[.!?…,]\W*$", cur):
                cur += ","
            cur += " — " + s                    # oznaka govornika ("rekao je")
            prev = "tag"
        else:
            if cur is not None:
                out.append(("d", cur))
            cur = None
            out.append(("o", pending + s))
            pending = ""
            prev = "n"
    if cur is not None:
        out.append(("d", cur))
    return out


def _gradi_dash(t, razdvoji):
    """— A. — rekao je. — B.  ->  ['— A. — rekao je.', '— B.'] (ako razdvoji)."""
    m = _DASH_START.match(t)
    lead = "".join(c for c in m.group(0) if _PH_LO <= c <= _PH_HI)
    parts = [x.strip() for x in _INT_DASH.split(t[m.end():]) if x.strip()]
    if not parts:
        return [t]
    turns = []
    cur = lead + "— " + parts[0]
    for prev, part in zip(parts, parts[1:]):
        if razdvoji and _veliko(part) and re.search(r"[.!?…]\W*$", prev):
            turns.append(cur)
            cur = "— " + part
        else:
            cur += " — " + part
    turns.append(cur)
    return turns


def pretvori_odlomak(html_inner, broj):
    """Vraca [(tip, html)] (tip 'd' dijalog / 'o' opis) ili None ako nema promjene."""
    masked, tags = _mask(html_inner)
    if len(tags) > 6000:
        return None
    t = masked.strip()
    razdvoji = broj >= 2
    if _DASH_START.match(t):
        dijelovi = [("d", x) for x in _gradi_dash(t, razdvoji)]
    else:
        dijelovi = _gradi_navodnici(t, razdvoji)
        if not dijelovi:
            return None
    return [(k, _unmask(s, tags)) for k, s in dijelovi]


def _zamijeni_odlomak(soup, p, broj):
    dijelovi = pretvori_odlomak(p.decode_contents(), broj)
    if not dijelovi:
        return False
    novi = []
    for kind, html in dijelovi:
        np_ = soup.new_tag("p")
        for ch in list(BeautifulSoup(html, "html.parser").contents):
            np_.append(ch)          # cuva <i>, <em>, <a> ...
        if kind == "d":
            np_["class"] = [CLS_DIJALOG]
        novi.append(np_)
    if p.get("id"):
        novi[0]["id"] = p["id"]
    for n in novi:
        p.insert_before(n)
    p.decompose()
    return True


# ═══ AI klasifikacija dijaloga ═══
BATCH_KLAS = 40
TIPOVI = ("opis", "dijalog", "dijalog+opis")


def ai_klasificiraj(tekstovi):
    """tekstovi: lista stringova -> {indeks: (tip, broj_govornika)} (samo uspjesno klasificirani)."""
    rez = {}
    for start in range(0, len(tekstovi), BATCH_KLAS):
        chunk = tekstovi[start:start + BATCH_KLAS]
        listing = "\n".join(f"[{j}] {t[:400].replace(chr(10), ' ')}"
                            for j, t in enumerate(chunk))
        prompt = f"""Analiziraj {len(chunk)} odlomaka knjige ispod.
Za SVAKI odlomak reci je li "dijalog", "opis" ili "dijalog+opis".

PRAVILA:
- "dijalog": odlomak je iskljucivo razgovor (pocinje crticom ili navodnicima, sav tekst je govor)
- "opis": pripovijedanje, opis scene, radnja, unutarnji monolog
- "dijalog+opis": sadrzi i govor i pripovijedanje (npr. '"Dosta!" rekao je dok je ustajao.')
- "broj_govornika": koliko RAZLICITIH osoba govori u tom odlomku (1 ili 2 ako ih je 2 i vise). Samo za dijalog i dijalog+opis.

KLJUCNO: crtica na pocetku NE znaci automatski dijalog. Nabrajanje, opis radnje s crticama,
pripovijedanje u prvom licu je "opis". Isto tako, pripovijedanje koje samo citira nadimak
ili naziv u navodnicima (npr. Zvali su ga "Vuk") je "opis".

VRATI JSON ARRAY (bez markdowna):
[
  {{"i": 0, "tip": "opis"}},
  {{"i": 1, "tip": "dijalog", "broj_govornika": 1}},
  {{"i": 2, "tip": "dijalog+opis", "broj_govornika": 2}}
]

ODLOMCI:
{listing}"""
        r = ai_call(prompt, "Vracas SAMO JSON. Bez markdowna, bez objasnjenja.", max_tokens=3000)
        for item in _kao_listu(parse_json(r)):
            if not isinstance(item, dict):
                continue
            j, tip = item.get("i"), item.get("tip")
            if not isinstance(j, int) or not 0 <= j < len(chunk) or tip not in TIPOVI:
                continue
            try:
                broj = int(item.get("broj_govornika") or 1)
            except (TypeError, ValueError):
                broj = 1
            rez[start + j] = (tip, broj)
    return rez


def klasificiraj_i_primijeni(soup):
    """Vraca (broj_kandidata, broj_zamijenjenih_odlomaka, broj_bez_AI_odgovora)."""
    body = soup.find("body")
    if not body:
        return 0, 0, 0
    ps = body.find_all("p")
    kandidati = []
    for i, p in enumerate(ps):
        if p.find_parent("div", class_=CLS_DC_BLOCK) or CLS_DIJALOG in _klase(p):
            continue
        t = p.get_text().strip()
        if t and _je_kandidat(t):
            kandidati.append((i, t))
    if not kandidati:
        return 0, 0, 0

    ai = ai_klasificiraj([t for _, t in kandidati])
    zamjene, bez_ai = [], 0
    for j, (i, t) in enumerate(kandidati):
        if j in ai:
            tip, broj = ai[j]
        else:                                   # fallback: samo ono sto ocito izgleda kao dijalog
            bez_ai += 1
            tip, broj = ("dijalog", 1) if _pocinje_dijalogom(t) else ("opis", 1)
        if tip != "opis":
            zamjene.append((ps[i], broj))
    n = sum(1 for p, broj in zamjene if _zamijeni_odlomak(soup, p, broj))
    return len(kandidati), n, bez_ai


# ═══ Ostali AI pozivi ═══
SCENE = ("battle", "romance", "death", "dialog", "description", "intro")


def ai_naslovi(files_data):
    """Za fajlove bez <h1-h3>: je li prvi redak naslov? -> {fname: naslov}."""
    out = {}
    for start in range(0, len(files_data), 60):
        chunk = files_data[start:start + 60]
        lines = []
        for i, fd in enumerate(chunk):
            lines.append(f"[{i}] {fd['fname'].split('/')[-1]}")
            lines.append(f"    RED1: {fd['prvi_redak'][:100]}")
            if fd.get("drugi_redak"):
                lines.append(f"    RED2: {fd['drugi_redak'][:100]}")
        prompt = (
            "Za svaki fajl knjige ispod reci je li PRVI REDAK naslov poglavlja.\n"
            "Naslov je: kratak (<60 znakova), obicno bez tocke na kraju, "
            "cesto ime osobe/mjesta ili rimski broj ili 'Poglavlje N'.\n"
            "Ako RED1 NIJE naslov, vrati naslov=null.\n\n"
            "VRATI SAMO JSON ARRAY:\n"
            '[{"i": 0, "naslov": null}, {"i": 1, "naslov": "Povratak kući"}]\n\n'
            "FAJLOVI:\n" + "\n".join(lines)
        )
        r = ai_call(prompt, "Vracas SAMO JSON.", max_tokens=3000)
        for item in _kao_listu(parse_json(r)):
            if not isinstance(item, dict):
                continue
            i, n = item.get("i"), item.get("naslov")
            if isinstance(i, int) and 0 <= i < len(chunk) and isinstance(n, str) and n.strip():
                out[chunk[i]["fname"]] = n.strip()
    return out


def _uzorak(tekst, n=1500):
    """Pocetak + sredina + kraj poglavlja (scena se ne vidi samo iz prvih 1500 znakova)."""
    if len(tekst) <= n:
        return tekst
    k, mid = n // 3, len(tekst) // 2
    return tekst[:k] + " [...] " + tekst[mid - k // 2: mid + k // 2] + " [...] " + tekst[-k:]


def ai_meta(tekst, treba_naslov):
    """Jedan poziv za tip scene (+ naslov ako ga poglavlje nema). -> (scena, naslov|None)"""
    if not tekst:
        return "description", None
    polja = '"scena": "battle|romance|death|dialog|description|intro"'
    if treba_naslov:
        polja += ', "naslov": "kratak naslov 3-6 rijeci na bosanskom/hrvatskom koji sazima radnju"'
    prompt = ("Za ovo poglavlje knjige vrati JSON objekt: {" + polja + "}\n"
              "Scena = dominantni tip poglavlja. Bez navodnika oko naslova, bez tocke.\n\n"
              "TEKST:\n" + _uzorak(tekst))
    data = parse_json(ai_call(prompt, "Vracas SAMO JSON objekt.", max_tokens=150, timeout=60))
    if isinstance(data, list) and data:
        data = data[0]
    scena, naslov = "description", None
    if isinstance(data, dict):
        s = str(data.get("scena", "")).strip().lower()
        if s in SCENE:
            scena = s
        n = data.get("naslov")
        if treba_naslov and isinstance(n, str):
            n = n.strip().strip("\"'„“”.").strip()
            if 3 <= len(n) <= 100:
                naslov = n
    return scena, naslov


# ═══ Slike kao pravi EPUB resursi ═══
class Resursi:
    """Ornament/dropcap slike idu jednom u zip + <manifest>, a poglavlja ih samo
    referenciraju (umjesto base64 u svakom poglavlju). Bez OPF-a pada na data: URI."""

    def __init__(self, opf_path):
        self.opf_path = opf_path
        self.koristeno = {}     # zip_path -> (Path, mime)

    def href(self, png, ime, chapter_fname):
        mime = _mime(str(png))
        if self.opf_path is None:
            return f"data:{mime};base64,{_b64(str(png))}"
        opf_dir = posixpath.dirname(self.opf_path)
        zip_path = posixpath.join(opf_dir, RES_SUBDIR, ime + _EXT[mime])
        self.koristeno[zip_path] = (png, mime)
        return posixpath.relpath(zip_path, posixpath.dirname(chapter_fname) or ".")

    def upisi(self, files):
        """Dodaj slike u zip-dict i u <manifest>. Ponovno pokretanje ne dupla stavke."""
        if not self.koristeno:
            return 0
        opf = files[self.opf_path].decode("utf-8", errors="replace")
        opf_dir = posixpath.dirname(self.opf_path)
        m = re.search(r"</((?:[\w.-]+:)?)manifest\s*>", opf)
        if not m:
            raise ValueError("OPF nema </manifest>")
        prefix, novi = m.group(1), []
        for zip_path, (png, mime) in self.koristeno.items():
            files[zip_path] = png.read_bytes()
            href = posixpath.relpath(zip_path, opf_dir or ".")
            if re.search(r"""href\s*=\s*["']%s["']""" % re.escape(href), opf):
                continue
            id_ = "booklyfi-" + re.sub(r"[^A-Za-z0-9_-]", "_",
                                       posixpath.splitext(posixpath.basename(zip_path))[0])
            novi.append(f'<{prefix}item id="{id_}" href="{href}" media-type="{mime}"/>')
        if novi:
            opf = opf[:m.start()] + "\n".join(novi) + "\n" + opf[m.start():]
            files[self.opf_path] = opf.encode("utf-8")
        return len(self.koristeno)


# ═══ HTML elementi ═══
def ocisti_stare(soup):
    # dropcap: vrati slovo u odlomak prije brisanja slike (inace se pri ponovnom
    # pokretanju prvo slovo poglavlja gubi)
    for img in soup.find_all("img", class_=CLS_DC_IMG):
        slovo = img.get("alt", "")
        blok = img.find_parent("div", class_=CLS_DC_BLOCK) or img
        nxt = blok.find_next_sibling("p")
        if slovo and nxt is not None:
            for node in nxt.find_all(string=True):
                s = str(node)
                if s.strip():
                    lead = len(s) - len(s.lstrip())
                    node.replace_with(s[:lead] + slovo + s[lead:])
                    break
        blok.decompose()
    for cls in ("booklyfi-ornament", CLS_DC_BLOCK, "booklyfi-vijenac"):
        for el in soup.find_all(class_=cls):
            el.decompose()
    for p in soup.find_all("p", class_=CLS_PRVI):
        ostalo = [c for c in _klase(p) if c != CLS_PRVI]
        if ostalo:
            p["class"] = ostalo
        else:
            del p["class"]


def _slicno(a, b):
    def n(s):
        return re.sub(r"[\W_]+", " ", s.casefold()).strip()
    a, b = n(a), n(b)
    if not a or not b:
        return False
    kraci, duzi = sorted((a, b), key=len)
    # jednako, ili jedno sadrzano u drugom i barem 70% duljine (AI moze malo preurediti naslov)
    return kraci == duzi or (kraci in duzi and len(kraci) >= 0.7 * len(duzi))


def _naslov_element(soup):
    """Prvi <title> iz <head> (ako nije generički), <h1>-<h3>, ili <p> naslov.
    
    NAPOMENA: poziva se PRIJE _strip_everything, na originalnom HTML-u.
    Prioritet:
      1. <title> iz <head> — pravi naslov poglavlja (Calibre)
      2. <h1>-<h3> — standardni HTML naslovi
      3. <p> koji izgleda kao naslov
    """
    # ── 1. <title> iz <head> ────────────────────────────────
    title = soup.find("title")
    if title:
        t = title.get_text(" ", strip=True)
        if t and len(t) < 100:
            # Preskoči generičke naslove
            genericki = (
                "poglavlje ", "chapter ", "section ", "part ",
                "stranica ", "page ", "untitled", "bez naslova",
                "cover", "naslovna", "sadržaj", "toc",
            )
            t_low = t.lower()
            if not any(t_low.startswith(g) for g in genericki):
                # Napravi lažni <p> tag sa ovim tekstom
                fake = soup.new_tag("p")
                fake.string = t
                return fake
    
    # ── 2. <h1>-<h3> ────────────────────────────────────────
    h = soup.find(["h1", "h2", "h3"])
    if h and not any(p.get_text(strip=True) for p in h.find_all_previous("p")):
        # Provjeri da nije generički ("Poglavlje N")
        h_text = h.get_text(" ", strip=True)
        h_low = h_text.lower()
        if not any(h_low.startswith(g) for g in (
            "poglavlje ", "chapter ", "section ", "part ",
            "stranica ", "page ",
        )):
            return h
    
    # ── 3. <p> koji izgleda kao naslov ──────────────────────
    body = soup.find("body")
    if not body:
        return None
    
    for i, p in enumerate(body.find_all("p")):
        if i > 5:
            break
        
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        
        if (len(text) < 60
            and text[0].isupper()
            and len(text.split()) <= 10):
            if "," not in text or len(text) < 40:
                return p
    
    return None


def izdvoji_naslov(soup, naslov_ai):
    body = soup.find("body")
    if not body:
        return naslov_ai, soup
    h = _naslov_element(soup)
    if h:
        n = h.get_text(" ", strip=True)
        h.decompose()
        return n or naslov_ai, soup
    if naslov_ai:
        for p in body.find_all("p"):
            t = p.get_text(" ", strip=True)
            if not t:
                continue
            if len(t) <= 120 and _slicno(t, naslov_ai):
                p.decompose()
            break
        return naslov_ai, soup
    return None, soup


def dodaj_ornament(soup, scena, res, fname):
    """Vraca True ako je ornament dodan."""

    # ZASTITA: ako vec postoji ornament, ne diraj
    if soup.find("div", class_="booklyfi-ornament"):
        return

    body = soup.find("body")
    k = _nadji_ornament(scena)
    if not body or k is None:
        return False
    div = soup.new_tag("div", attrs={"class": ["booklyfi-ornament"], "style": STYLE_ORN})
    img = soup.new_tag("img", attrs={
        "src": res.href(k, k.stem.lower(), fname),
        "alt": "*", "style": STYLE_ORN_IMG})
    div.append(img)
    body.insert(0, div)
    return True


def dodaj_naslov(soup, naslov):
    body = soup.find("body")
    if not body or not naslov:
        return
    h1 = soup.new_tag("h1", attrs={"class": [CLS_NASLOV]})
    h1.string = naslov
    orn = body.find("div", class_="booklyfi-ornament")
    if orn:
        orn.insert_after(h1)
    else:
        body.insert(0, h1)


def _nadji_inicijal(p):
    """(text_node, tekst, indeks_prvog_slova) ako odlomak pocinje slovom (proza), inace None."""
    for node in p.find_all(string=True):
        s = str(node)
        idx = next((i for i, c in enumerate(s) if c.isalpha()), None)
        if idx is None:
            if s.strip():
                return None          # pocinje crticom/navodnikom/brojem
            continue
        if s[:idx].strip():
            return None
        return node, s, idx
    return None


def dodaj_dropcap(soup, res, fname):
    """Dropcap na prvi PRAVI odlomak poglavlja.

    Pravila:
      - Preskače <h1>-<h6> i klase naslova
      - Preskače dijalog (—, –, -)
      - Preskače citate ("...", „...", "...")
      - Preskače <p> < 60 znakova
      - Preskače <p> koji je samo broj
      - Traži prvi <p> koji počinje VELIKIM SLOVOM
      - Ubacuje nevidljivo slovo za TTS u <span style="font-size:1px;color:transparent">

    Struktura izlaza:
      <p class="booklyfi-prvi" style="...">
        <img class="booklyfi-dropcap" src="images/booklyfi/dc_XXXX.png"/>
        <span style="font-size:1px;color:transparent;line-height:0;">C</span>alder je sjedio...
      </p>
    """
    body = soup.find("body")
    if not body:
        return

    # FIX: ukloni postojeći dropcap (img + span) prije dodavanja novog
    for img in soup.find_all("img", class_="booklyfi-dropcap"):
        img.decompose()
    for span in soup.find_all("span", style=lambda s: s and "font-size:1px" in s):
        span.decompose()
    for span in soup.find_all("span", style=lambda s: s and "font-size:0" in s):
        span.decompose()
    for div in soup.find_all("div", class_="booklyfi-dropcap-block"):
        div.decompose()

    SKIP_KLASE = {
        "chapter-title", "chapter-number", "chapter-number-title",
        "booklyfi-naslov", "chapter_subtitle", "subtitle",
        "title", "naslov", "epigraph", "quote", "blockquote",
        "chapter-heading", "chapterheader",
    }

    def _je_naslov(tag):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return True
        klase = tag.get("class") or []
        if isinstance(klase, str):
            klase = klase.split()
        for k in klase:
            if k.lower() in SKIP_KLASE:
                return True
        return False

    def _je_citat(t):
        if not t:
            return False
        if t[0] in ('"', '„', '“', '«', '‹', "'", '‚', '‘'):
            return True
        if any(c in '"„""«' for c in t[:5]):
            return True
        return False

    for p in body.find_all("p"):
        if _je_naslov(p):
            continue

        text = p.get_text(strip=True)
        if len(text) < 60:
            continue
        if text.isdigit():
            continue
        if _je_citat(text):
            continue
        if text[0] in ("—", "–", "-", "‒", "―"):
            continue
        if not text[0].isalpha() or not text[0].isupper():
            continue

        # Prvo slovo
        first_char = None
        for content in p.contents:
            if isinstance(content, str):
                s = content.strip()
                if s:
                    first_char = s[0].upper()
                break
            elif hasattr(content, "get_text"):
                t = content.get_text(strip=True)
                if t:
                    first_char = t[0].upper()
                break

        if not first_char or not first_char.isalpha():
            continue

        # Digraf?
        dig = first_char
        try:
            s_tekst = p.get_text(strip=True)
            if len(s_tekst) >= 2:
                d2 = s_tekst[:2].upper()
                if d2 in DIGRAFI and d2 in DROPCAP_MAP:
                    dig = d2
        except Exception:
            pass

        if dig in DROPCAP_MAP:
            kljuc = dig
            n = 2 if len(dig) == 2 else 1
        else:
            kljuc = first_char
            n = 1

        png = DROPCAP_MAP.get(kljuc)
        if not png:
            continue

        ime = "dc_" + "_".join(f"{ord(c):04x}" for c in kljuc)

        # Uzmi puni tekst i izreži
        s_pun = p.get_text("", strip=False)
        idx = s_pun.find(kljuc) if kljuc in s_pun else s_pun.upper().find(kljuc)
        if idx < 0:
            idx = 0
        slovo = s_pun[idx:idx+n] if idx+n <= len(s_pun) else kljuc
        ostatak = s_pun[idx+n:].lstrip() if s_pun[idx+n:idx+n+1].isspace() else s_pun[idx+n:]
        # FIX: očisti duple ponavljajuće prvo slovo (AAAutorska → Autorska)
        # (nastaje zbog prethodnih stilizacija koje su vraćale span u tekst)
        if slovo and ostatak:
            while ostatak.startswith(slovo):
                ostatak = ostatak[len(slovo):]

        # Napravi img i span
        img = soup.new_tag("img", attrs={
            "class": "booklyfi-dropcap",
            "src": res.href(png, ime, fname),
            "alt": slovo,
            "style": (
                "float:left;display:inline;width:2.5em;height:auto;"
                "max-width:none;margin:0.05em 0.15em 0 0;padding:0;"
                "vertical-align:top;"
            ),
        })

        span = soup.new_tag("span", attrs={
            "style": "color:transparent;font-size:1px;line-height:0;"
        })
        span.string = slovo

        # Očisti <p> i ubaci novo
        p.clear()
        p.append(img)
        p.append(span)
        p.append(ostatak)

        klase = p.get("class") or []
        if isinstance(klase, str):
            klase = klase.split()
        klase.append("booklyfi-prvi")
        p["class"] = klase

        return


def primijeni_inline(soup):
    body = soup.find("body")
    if body:
        body["style"] = STYLE_BODY
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        h["style"] = STYLE_H1 if CLS_NASLOV in _klase(h) else STYLE_H2
    prekid = True   # prvi odlomak i odlomak nakon prekida scene = bez uvlake
    for p in (body or soup).find_all("p"):
        if p.find_parent("div", class_=CLS_DC_BLOCK):
            continue
        t = p.get_text(strip=True)
        if not t:
            continue
        if CLS_DIJALOG in _klase(p):
            p["style"] = STYLE_DIALOG
            prekid = False
        elif _je_prekid(t):
            p["style"] = STYLE_BREAK
            prekid = True
        else:
            p["style"] = STYLE_P_FIRST if (prekid or CLS_PRVI in _klase(p)) else STYLE_P
            prekid = False


# ═══ EPUB helperi ═══


# ── Zaštita: provjeri/regeneriraj container.xml prije pisanja ──
def _osiguraj_container_xml(files):
    """Ako je META-INF/container.xml pokvaren, regeneriraj ga iz OPF putanje."""
    cname = "META-INF/container.xml"
    if cname not in files:
        # Nema ga — napravi novi
        opf_path = None
        for name in files:
            if isinstance(name, str) and name.lower().endswith(".opf"):
                opf_path = name
                break
        if not opf_path:
            return False
        new_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '  <rootfiles>\n'
            f'    <rootfile full-path="{opf_path}" '
            'media-type="application/oebps-package+xml"/>\n'
            '  </rootfiles>\n'
            '</container>\n'
        )
        files[cname] = new_xml.encode("utf-8")
        return True

    raw = files[cname]
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
        files[cname] = raw

    # Je li XML?
    if b"<container" in raw[:500].lower():
        return False

    # Pokvaren — regeneriraj
    opf_path = None
    for name in files:
        if isinstance(name, str) and name.lower().endswith(".opf"):
            opf_path = name
            break

    if not opf_path:
        return False

    new_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        f'    <rootfile full-path="{opf_path}" '
        'media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )
    files[cname] = new_xml.encode("utf-8")
    return True



def popravi_container(files):
    """Ako je META-INF/container.xml pokvaren (npr. AI odgovor), regeneriraj ga."""
    cname = "META-INF/container.xml"
    if cname not in files:
        return False
    
    raw = files[cname]
    # Je li XML? Ako sadrzi <container u prvih 500 bajtova — OK
    if b"<container" in raw[:500].lower():
        return False
    
    # Pokvaren — regeneriraj
    opf_path = None
    for name in files:
        if name.lower().endswith(".opf"):
            opf_path = name
            break
    
    if not opf_path:
        print("   UPOZORENJE: container.xml pokvaren, ne mogu naci OPF")
        return False
    
    new_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        f'    <rootfile full-path="{opf_path}" '
        'media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )
    files[cname] = new_xml.encode("utf-8")
    print(f"   Popravljen container.xml -> {opf_path}")
    return True


def nadji_opf(files):
    try:
        cont = BeautifulSoup(files["META-INF/container.xml"], "html.parser")
        opf_path = cont.find("rootfile")["full-path"]
    except Exception:
        return None
    return opf_path if opf_path in files else None


def spine_redoslijed(files, opf_path):
    if not opf_path:
        return []
    opf = BeautifulSoup(files[opf_path], "html.parser")
    baza = posixpath.dirname(opf_path)
    manifest = {it["id"]: it["href"] for it in opf.find_all("item")
                if it.get("id") and it.get("href")}
    out = []
    for ref in opf.find_all("itemref"):
        href = manifest.get(ref.get("idref"))
        if href:
            out.append(posixpath.normpath(
                posixpath.join(baza, unquote(href.split("#")[0]))))
    return out


def _prirodni(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def _preskoci(fname):
    tokeni = re.split(r"[^a-z0-9]+", Path(fname).stem.lower())
    return any(re.fullmatch(r"(toc|nav|cover|titlepage|copyright)\d*", t) for t in tokeni)

# DODANO: preskoci META-INF i container.xml
_original_preskoci = _preskoci

def _preskoci(n):
    import os as _os
    n_lower = str(n).lower()
    base = _os.path.basename(n_lower)

    # META-INF i sve XML
    if 'meta-inf' in n_lower or 'meta_inf' in n_lower:
        return True
    if base in ('container.xml', 'mimetype', 'content.opf', 'toc.ncx'):
        return True
    if 'container' in base and base.endswith('.xml'):
        return True

    # Tehnicke stranice
    tehnicke = ('cover', 'titlepage', 'copyright', 'colophon',
                'toc', 'sadrzaj', 'nav', 'abouttheauthor', 'about-author',
                'ad-card', 'adcard', 'acknowledgements', 'acknowledgments',
                'appendix', 'newsletter', 'praise', 'teaser',
                'dedication', 'posveta', 'welcome', 'dobrodosli',
                'preface', 'predgovor', 'intro', 'uvod')
    for t in tehnicke:
        if base.startswith(t) or base.endswith(t + '.xhtml') or base.endswith(t + '.html'):
            return True

    # .ncx, .opf, .xml
    if base.endswith(('.ncx', '.opf', '.xml')):
        return True

    return _original_preskoci(n)

def nadji_poglavlja(files, opf_path):
    """Vraća listu (fname, html_str) tuple-ova za sva poglavlja."""
    ext = (".html", ".xhtml", ".htm")
    spine = [n for n in spine_redoslijed(files, opf_path) if n in files and n.lower().endswith(ext)]
    if spine:
        nazivi = list(dict.fromkeys(spine))
    else:
        nazivi = sorted((n for n in files if n.lower().endswith(ext)), key=_prirodni)
    rezultat = []
    for n in nazivi:
        if _preskoci(n):
            continue
        try:
            html = files[n].decode("utf-8", errors="replace")
        except Exception:
            continue
        rezultat.append((n, html))
    return rezultat

def snimi_epub(src, files):
    out = Path(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".epub.tmp", dir=out.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            if "mimetype" in files:
                z.writestr("mimetype", files["mimetype"], compress_type=zipfile.ZIP_STORED)
            for n, d in files.items():
                if n == "mimetype" or n.endswith("/"):
                    continue
                z.writestr(n, d, compress_type=zipfile.ZIP_DEFLATED)
        # Copymode samo ako izvor postoji
        if out.exists():
            try:
                shutil.copymode(out, tmp)
            except Exception:
                pass
        os.replace(tmp, out)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _osiguraj_css(soup):
    """Osiguraj da svaki HTML ima <style> blok sa CSS_BLOCK."""
    head = soup.find("head")
    if not head:
        head = soup.new_tag("head")
        soup.insert(0, head)
    # Ukloni postojeće prazne style tagove
    for st in head.find_all("style"):
        st.decompose()
    style_tag = soup.new_tag("style")
    style_tag.string = CSS_BLOCK
    head.append(style_tag)
    return soup

def _pripremi_soup(html):
    """Parsira HTML i stripuje SVE stilove/klase/slike/spanove.

    Rezultat: goli HTML (<h1>-<h6>, <p>, <br>, <em>, <i>, <b>, <strong>).
    Ovo garantuje da svaka knjiga izlazi identično bez obzira na ulaz.
    """
    soup = BeautifulSoup(html, "html.parser")
    try:
        from epub.normalizer import _strip_everything
        _strip_everything(soup)
    except Exception as e:
        print(f"      ⚠ strip greška: {e}")
        # FIX: ubaci CSS blok u <style>
    _osiguraj_css(soup)
    return soup


def obradi_poglavlje(html, naslov_ai, redni, ukupno, fname, res, log_callback=None):
    """Obrada jednog poglavlja.

    Redoslijed (VAŽNO):
      1. Parsiraj HTML
      2. STRIP sve (idempotentnost)
      3. Izvuci naslov (postojeći ili AI)
      4. AI klasifikacija scene (battle/death/romance/dialog/description/intro)
      5. Klasificiraj dijalog (—, –, -)
      6. Dodaj ornament za scenu (ornament_<scena>.png)
      7. Dodaj naslov (h1)
      8. Dodaj dropcap (samo na prvi pravi pasus)
      9. Primeni inline stilove
    """
    # 1-2. Parse + strip
    soup = _pripremi_soup(html)

    # 3. Naslov
    naslov, soup = izdvoji_naslov(soup, naslov_ai)

    # 4. AI klasifikacija scene
    scena, gen = ai_meta(soup.get_text(" ", strip=True), treba_naslov=not naslov)
    # FIX: ne generiši "Poglavlje N" — bolje prazno nego generički
    # (styler.py će poslije probati iz <p>)
    naslov = naslov or gen
    _msg = f"[{redni:2d}/{ukupno}] {naslov[:45]:45s} | scena: {scena}"
    print(_msg)
    if log_callback:
        try: log_callback(_msg, "info")
        except Exception: pass

    # 5. Dijalog
    n_kand, n_zam, n_bez = klasificiraj_i_primijeni(soup)
    if n_kand:
        _dmsg = (f"      dijalog: {n_kand} kandidata, {n_zam} odlomaka preoblikovano"
                 + (f", {n_bez} bez AI odgovora (heuristika)" if n_bez else ""))
        print(_dmsg)
        if log_callback:
            try: log_callback(_dmsg, "tech")
            except Exception: pass

    # 6. Ornament za scenu
    if not dodaj_ornament(soup, scena, res, fname) and scena not in _UPOZORENO:
        _UPOZORENO.add(scena)
        _omsg = f"      UPOZORENJE: nema ornamenta za scenu '{scena}'"
        print(_omsg)
        if log_callback:
            try: log_callback(_omsg, "warning")
            except Exception: pass

    # 7. Naslov (h1) — SAMO ako već ne postoji
    if not soup.find("h1"):
        dodaj_naslov(soup, naslov)
    else:
        # Već ima h1 — ne dodavaj novi
        pass

    # 8. Dropcap
    dodaj_dropcap(soup, res, fname)

    # 9. Inline stilovi
    primijeni_inline(soup)
    return str(soup)


def stilizuj_epub(epub_path, output_path=None, log_callback=None):
    """Programski ulaz za stilizaciju EPUB-a.

    Prima putanju ulaznog EPUB-a, vraća dict sa statusom.
    Može se pozvati iz Flask endpointa.

    :param epub_path:     ulazni EPUB
    :param output_path:   izlazni EPUB (ako None → prepiše ulazni)
    :param log_callback:  funkcija(msg, tip) za live audit
    :returns:             {"ok": bool, "output": str, "greska": str|None,
                           "poglavlja": int, "dropcapovi": int}
    """
    import os, zipfile, tempfile
    from pathlib import Path as _P

    def _log(msg, tip="info"):
        if log_callback:
            try:
                log_callback(msg, tip)
            except Exception:
                pass
        print(f"  [{tip}] {msg}")

    rezultat = {"ok": False, "output": None, "greska": None,
                "poglavlja": 0, "dropcapovi": 0}

    epub_path = _P(epub_path)
    if not epub_path.exists():
        rezultat["greska"] = f"EPUB ne postoji: {epub_path}"
        return rezultat

    output_path = _P(output_path) if output_path else None

    try:
        # Učitaj EPUB u dict {name: bytes}
        with zipfile.ZipFile(epub_path) as z:
            files = {n: z.read(n) for n in z.namelist()}

        # ── Odabir izlazne putanje ──
        if output_path is None:
            try:
                from epub.styler import (
                    _extract_book_metadata,
                    _build_normalized_name,
                    STYLED_OUTPUT_DIR,
                )
                creator, title = _extract_book_metadata(files)
                out_dir = _P(STYLED_OUTPUT_DIR)
                out_dir.mkdir(parents=True, exist_ok=True)
                output_path = out_dir / _build_normalized_name(creator, title, "PREVEDENO_STYLED")
                _log(f"Izlaz: {output_path.name}", "system")
            except Exception as _e:
                _log(f"Ne mogu odrediti STYLED putanju ({_e}) — koristim _PREVEDENO_STYLED pored originala", "warning")
                output_path = epub_path.with_name(epub_path.stem + "_PREVEDENO_STYLED" + epub_path.suffix)

        # Inicijalizuj fleet
        if _AI["fleet"] is None:
            if not init_fleet():
                _log("Fleet nije dostupan — nastavljam bez AI klasifikacije scene", "warning")

        # Učitaj dropcap mape
        ucitaj_dropcap()
        _log(f"Dropcap PNG: {len(DROPCAP_MAP)}", "tech")

        # Nađi OPF
        # Osiguraj container.xml (ako fali)
        if "META-INF/container.xml" not in files:
            try:
                _osiguraj_container_xml(files)
                _log("Generiran container.xml", "tech")
            except Exception as e:
                _log(f"container.xml greška: {e}", "warning")
        
        opf_path = nadji_opf(files)
        if not opf_path:
            rezultat["greska"] = "Nema OPF-a u EPUB-u"
            return rezultat

        res = Resursi(opf_path)

        # Nađi poglavlja
        poglavlja = nadji_poglavlja(files, opf_path)
        _log(f"Poglavlja: {len(poglavlja)}", "info")

        ukupno = len(poglavlja)
        for redni, (fname, html) in enumerate(poglavlja, 1):
            try:
                _log(f"▶ Poglavlje {redni}/{ukupno}: {fname}", "system")
                novi_html = obradi_poglavlje(
                    html,
                    naslov_ai=None,
                    redni=redni,
                    ukupno=ukupno,
                    fname=fname,
                    res=res,
                    log_callback=log_callback,
                )
                files[fname] = novi_html.encode("utf-8")
            except Exception as e:
                _log(f"Greška u poglavlju {fname}: {e}", "warning")
                continue

        # Upiši slike u zip
        n_slika = res.upisi(files)
        _log(f"Dodano slika: {n_slika}", "tech")

        # Sačuvaj EPUB

        # Standardizuj metapodatke
        try:
            from core.metadata import standardizuj_metapodatke
            from datetime import datetime as _dt
            _stats_meta = standardizuj_metapodatke(
                files=files,
                opf_path=opf_path,
                epub_path=str(output_path),
                stylized_at=_dt.now().isoformat(timespec='seconds'),
                pipeline_version='V10_TURBO',
            )
            if _stats_meta.get('ok'):
                _log('Metadata standardizovani (' + str(_stats_meta['booklyfi_meta_added']) + ' booklyfi polja)', 'tech')
        except Exception as _e:
            _log('Metadata greška: ' + str(_e), 'warning')
        snimi_epub(output_path, files)
        _log(f"Sačuvano: {output_path}", "info")

        rezultat["ok"] = True
        rezultat["output"] = str(output_path)
        rezultat["poglavlja"] = ukupno
        rezultat["dropcapovi"] = ukupno  # aproksimacija
        return rezultat

    except Exception as e:
        import traceback
        rezultat["greska"] = f"{type(e).__name__}: {e}"
        _log(f"GREŠKA: {rezultat['greska']}", "warning")
        traceback.print_exc()
        return rezultat


def _safe_copy(src, dst):
    """Kopiraj fajl, ali preskoči ako su isti."""
    from pathlib import Path as _P
    import shutil as _sh
    src_p = _P(src)
    dst_p = _P(dst)
    try:
        if src_p.resolve() == dst_p.resolve():
            print(f"   (isti fajl — preskačem kopiju)")
            return
    except Exception:
        pass
    try:
        if src_p.samefile(dst_p):
            print(f"   (isti fajl — preskačem kopiju)")
            return
    except (OSError, FileNotFoundError):
        pass
    _sh.copy2(src, dst)


def main():
    if "--ornamenti" in sys.argv:       # samo dijagnostika ornamenata, bez EPUB-a
        ucitaj_dropcap()
        provjeri_ornamente()
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bez_ai = "--bez-ai" in sys.argv
    if not args:
        print("Koristenje: python3 stil_ai.py <knjiga.epub> [--bez-ai]")
        sys.exit(1)
    src = args[0]
    if not Path(src).exists():
        print(f"Ne postoji: {src}")
        sys.exit(1)

    if not bez_ai and not init_fleet():
        sys.exit(1)
    ucitaj_dropcap()
    print(f"Dropcap PNG: {len(DROPCAP_MAP)}")
    provjeri_ornamente()
    print(f"Knjiga: {Path(src).name}")
    print(f"Veličina: {Path(src).stat().st_size / 1024:.1f} KB")

    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = f"{src}.bak_{ts}"
    _safe_copy(src, backup)
    print(f"Backup: {backup}\n")

    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

    popravi_container(files)
    opf_path = nadji_opf(files)
    if not opf_path:
        print("UPOZORENJE: OPF nije nadjen, slike idu kao base64 u svako poglavlje")
    res = Resursi(opf_path)
    html_names = nadji_poglavlja(files, opf_path)
    print(f"HTML fajlova: {len(html_names)}\n")

    # FAZA 1: priprema
    import time as _time
    _t0 = _time.time()
    print(f"\n{'═' * 60}")
    print(f"[FAZA 1/3] Priprema — parsiranje HTML fajlova...")
    print(f"{'═' * 60}")
    files_data = []
    for fname, _html_tuple in html_names:
        soup = BeautifulSoup(files[fname].decode("utf-8", errors="replace"), "html.parser")
        body = soup.find("body")
        if not body or len(body.get_text(strip=True)) < 100:
            continue
        ps = [t for t in (p.get_text(" ", strip=True) for p in body.find_all("p")) if t]
        files_data.append({
            "fname": fname,
            "prvi_redak": ps[0] if ps else body.get_text(" ", strip=True)[:100],
            "drugi_redak": ps[1] if len(ps) > 1 else "",
            "ima_naslov": _naslov_element(soup) is not None,
        })
    print(f"   Validnih: {len(files_data)}\n")

    # FAZA 2: AI naslovi (samo za poglavlja bez h1-h3)
    print(f"\n{'═' * 60}")
    print(f"[FAZA 2/3] AI naslovi — samo za poglavlja bez naslova...")
    print(f"{'═' * 60}")
    treba = [fd for fd in files_data if not fd["ima_naslov"]]
    if treba:
        print(f"   {len(treba)} poglavlja bez naslova — šaljem na AI...")
        naslovi_map = ai_naslovi(treba)
        print(f"   {len(naslovi_map)}/{len(treba)} naslova prepoznato")
    else:
        naslovi_map = {}
        print(f"   Sva poglavlja imaju naslov — AI se ne poziva ✅")

    # FAZA 3: stilizacija
    print(f"\n{'═' * 60}")
    print(f"[FAZA 3/3] Stilizacija — {len(files_data)} poglavlja")
    print(f"{'═' * 60}")
    for i, fd in enumerate(files_data, 1):
        fname = fd["fname"]
        _pct = int(100 * i / len(files_data))
        _bar = "█" * (i * 30 // len(files_data)) + "░" * (30 - i * 30 // len(files_data))
        print(f"  [{i:3d}/{len(files_data)}] {_bar} {_pct:3d}%  {fname.split('/')[-1]:40s}", end="")
        try:
            html = files[fname].decode("utf-8", errors="replace")
            files[fname] = obradi_poglavlje(
                html, naslovi_map.get(fname), i, len(files_data), fname, res).encode("utf-8")
            print(" ✅")
        except Exception as e:
            print(f" ❌ {type(e).__name__}: {e}")

    # Snimanje — u STYLED_OUTPUT_DIR (ne in-place!)
    print("\nSnimanje...")
    try:
        if opf_path:
            print(f"   Slika u manifestu: {res.upisi(files)}")

        # ── Odabir izlazne putanje: STYLED_OUTPUT_DIR ──
        out_path = src  # fallback
        try:
            from epub.styler import (
                _extract_book_metadata,
                _build_normalized_name,
                STYLED_OUTPUT_DIR,
            )
            creator, title = _extract_book_metadata(files)
            out_dir = Path(STYLED_OUTPUT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(out_dir / _build_normalized_name(creator, title, "PREVEDENO_STYLED"))
            print(f"   Izlaz: {out_path}")
        except Exception as _e:
            print(f"   UPOZORENJE: ne mogu odrediti STYLED putanju ({_e}), snimam pored originala")

        # Kopiraj original u novu putanju pa je prepiši stilizovanim sadržajem
        _safe_copy(src, out_path)
        snimi_epub(out_path, files)
    except Exception as e:
        print(f"   GRESKA: {e}\n   Original je netaknut, backup: {backup}")
        sys.exit(1)
    print(f"   Snimljeno: {out_path}")
    print(f"   {Path(out_path).stat().st_size / 1024:.1f} KB")
    print("\nGOTOVO")


if __name__ == "__main__":
    main()
