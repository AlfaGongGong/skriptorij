"""G3: deterministicka strukturna kapija prije upisa .chk (bez AI).

provjeri(en_html, hr_html, rel_glosar) vraca listu razloga (prazna = prolazi):
(a) broj <p>, (b) skup brojeva, (c) imena (velika slova), (d) replike, (e) negacije.
Konzervativne granice: kapija odbija najvise 2 puta pa prihvaca (fail-open, _kapija_odbij).
"""
import html as _html
import re

_P_RX = re.compile(r"<p[\s>]", re.I)
_P_BLOK = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_BROJ_RX = re.compile(r"\d+(?:[.,]\d+)*")
_GL_RX = re.compile(r"^-?\s*(.+?)\s*->\s*(.+?)(?:\s*\[[^\]]*\])?\s*$")
_IME_RX = re.compile(r"(?<![\w'’-])([A-Z][a-z]{2,})\b")

_IME_STOP = frozenset(
    "God Lord Lady Sir Miss Mrs Master Majesty Highness Grace Christmas Easter "
    "English French German Latin Monday Tuesday Wednesday Thursday Friday Saturday "
    "Sunday January February March April May June July August September October "
    "November December The And But For With This That What When Then There They "
    "She Her His Him You Your Not Now Yes Well Why How Who Where".split()
)
_NEG_EN = re.compile(
    r"n't\b|\b(?:not|never|no|nothing|nobody|none|neither|nor|nowhere|without|cannot)\b", re.I
)
_NEG_HR = re.compile(
    r"\b(?:ne|nije|nisam|nisi|nismo|niste|nisu|neću|nećeš|neće|nećemo|nećete|nema|nemam|"
    r"nemaš|nemamo|nemate|nemaju|nikad|nikada|nitko|nikoga|nikome|ništa|nijedan|nijedna|"
    r"nijedno|niti|bez)\b",
    re.I,
)
_REPLIKA_EN = ("\u2014", "\u2013", "-", '"', "\u201c", "\u2018", "'")
_REPLIKA_HR = ("\u2014", "\u2013", "-", '"', "\u201e", "\u201c", "\u00bb", "'")


def _plain(h: str) -> str:
    return _html.unescape(_TAG.sub(" ", h or ""))


def _paragrafi(h: str):
    return [_plain(m).strip() for m in _P_BLOK.findall(h or "")]


def _brojevi(plain: str) -> set:
    t = re.sub(r"(?<=\d)[.,](?=\d)", "", plain)
    return set(re.findall(r"\d+", t))


def _imena(plain: str) -> set:
    res = set()
    for m in _IME_RX.finditer(plain):
        if m.group(1) in _IME_STOP:
            continue
        pre = plain[: m.start()].rstrip()
        if not pre or pre[-1] in ".!?\u2026\"\u201c\u201d\u2018:;\u2014\u2013(":
            continue  # pocetak recenice, ne ime
        res.add(m.group(1))
    return res


def _glosar_mapa(rel_glosar) -> dict:
    mapa = {}
    for linija in str(rel_glosar or "").split("\n"):
        m = _GL_RX.match(linija.strip())
        if m:
            mapa[m.group(1).strip().lower()] = m.group(2).strip().lower()
    return mapa


def provjeri(en_html: str, hr_html: str, rel_glosar=None) -> list:
    razlozi = []
    if not en_html or not hr_html:
        return razlozi
    p_en = len(_P_RX.findall(en_html))
    p_hr = len(_P_RX.findall(hr_html))
    en_p, hr_p = _plain(en_html), _plain(hr_html)

    # (a) broj odlomaka
    if p_en >= 2 and (p_hr < p_en or p_hr > p_en * 1.5 + 1):
        razlozi.append("odlomci EN %d, HR %d" % (p_en, p_hr))

    # (b) brojevi
    be, bh = _brojevi(en_p), _brojevi(hr_p)
    if be != bh:
        razlozi.append("brojevi: samo u EN %s, samo u HR %s" % (sorted(be - bh)[:4], sorted(bh - be)[:4]))

    # (c) imena
    ime = _imena(en_p)
    if len(ime) >= 2:
        hr_low = hr_p.lower()
        mapa = _glosar_mapa(rel_glosar)
        nema = []
        for n in sorted(ime):
            nl = n.lower()
            kandidati = [nl, mapa.get(nl, "")]
            ok = False
            for k in kandidati:
                if k and k[: max(3, len(k) - 2)] in hr_low:
                    ok = True
                    break
            if not ok:
                nema.append(n)
        if len(nema) >= 2 and len(nema) / len(ime) >= 0.5:
            razlozi.append("imena nedostaju: " + ", ".join(nema[:5]))

    # (d) replike
    if p_en >= 3:
        re_en = sum(1 for p in _paragrafi(en_html) if p.startswith(_REPLIKA_EN))
        re_hr = sum(1 for p in _paragrafi(hr_html) if p.startswith(_REPLIKA_HR))
        if abs(re_en - re_hr) > max(1, re_en // 5):
            razlozi.append("replike EN %d, HR %d" % (re_en, re_hr))

    # (e) negacije
    n_en, n_hr = len(_NEG_EN.findall(en_p)), len(_NEG_HR.findall(hr_p))
    if n_en >= 4 and (n_hr < n_en * 0.4 or n_hr > n_en * 2.5 + 2):
        razlozi.append("negacije EN %d, HR %d" % (n_en, n_hr))
    return razlozi
