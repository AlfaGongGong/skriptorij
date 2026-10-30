"""
core/metrics.py — deterministicke metrike kvaliteta teksta.

Brojaci gresaka umjesto ocjene 1-10: uporedivo izmedju knjiga i kroz vrijeme.
Cista funkcija: bez AI poziva, bez mijenjanja postojeceg koda.
"""

import html
import re
from collections import Counter

from core.kalkovi.ekavizmi import EKAVIZMI
from core.quality import _ekstrahuj_cist_tekst
from core.text_utils import _detektuj_en_ostatke

# Pasusi kraci od ovoga se ne broje kao duplikati ("Da." u dijalogu je normalno)
MIN_RECI_DUPLIKAT = 4

_RE_RIJEC = re.compile(r"[^\W_]+")
_RE_P = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_BLOK = re.compile(r"</?(?:p|div|br|h[1-6]|li|blockquote|tr)\b[^>]*>", re.IGNORECASE)
_RE_RAZMAK = re.compile(r"[.,;:!?](?=[^\W\d_])")
_RE_CRTICA = re.compile(r"^\s*-\s*[^\W\d_]")
_RE_VELIKO = re.compile(r"([^\s.!?]+)([.!?])\s+(?=[^\W\d_])")

_SKRACENICE = frozenset(
    {
        "itd",
        "itp",
        "tj",
        "npr",
        "tzv",
        "ur",
        "god",
        "br",
        "sv",
        "str",
        "usp",
        "dr",
        "mr",
        "prof",
        "gđa",
        "gđica",
        "gosp",
        "sl",
        "vs",
        "etc",
        "cf",
        "mj",
        "tel",
        "ul",
        "ing",
        "dipl",
        "inž",
        "doc",
        "akad",
        "sr",
        "cca",
    }
)

_KOMPILIRANI = None


def _nule() -> dict:
    return {
        "ekavizmi_per_1000": 0.0,
        "en_ostaci_per_1000": 0.0,
        "duplikati": 0,
        "ratio_source_target": None,
        "tipografija_greske": 0,
        "reci_ukupno": 0,
    }


def _cist(tekst) -> str:
    try:
        return _ekstrahuj_cist_tekst(tekst) or ""
    except Exception:
        return ""


def _pasusi(tekst: str) -> list:
    """Pasusi iz HTML-a (<p>) ili plain texta (\\n\\n). JSON (.chk) se prvo ekstrahuje."""
    if tekst.lstrip().startswith("{"):
        tekst = _cist(tekst)
    nadjeno = _RE_P.findall(tekst)
    if nadjeno:
        izvori = nadjeno
    else:
        izvori = re.split(r"\n\s*\n", _RE_BLOK.sub("\n\n", tekst))
    out = []
    for iz in izvori:
        p = html.unescape(_RE_TAG.sub("", iz))
        if p.strip():
            out.append(p)
    return out


def _ekavizmi_obrasci() -> list:
    global _KOMPILIRANI
    if _KOMPILIRANI is None:
        lista = []
        for stavka in EKAVIZMI:
            try:
                lista.append(re.compile(stavka[0], re.IGNORECASE))
            except re.error:
                continue
        _KOMPILIRANI = lista
    return _KOMPILIRANI


def _broji_ekavizme(cist: str) -> int:
    """Pogodci koji se preklapaju (npr. 'pre nego sto' i 'pre nego') broje se jednom."""
    spans = []
    for rx in _ekavizmi_obrasci():
        for m in rx.finditer(cist):
            if m.end() > m.start():
                spans.append((m.start(), m.end()))
    if not spans:
        return 0
    spans.sort()
    n = 0
    kraj = -1
    for s, e in spans:
        if s >= kraj:
            n += 1
            kraj = e
        else:
            kraj = max(kraj, e)
    return n


def _broji_duplikate(pasusi: list) -> int:
    cnt = Counter()
    for p in pasusi:
        norm = " ".join(p.lower().split())
        if len(_RE_RIJEC.findall(norm)) >= MIN_RECI_DUPLIKAT:
            cnt[norm] += 1
    return sum(c - 1 for c in cnt.values() if c > 1)


def _tipografija_pasus(p: str) -> int:
    p = p.strip()
    n = 0

    # dupli razmak (novi redovi iz HTML formatiranja se ne racunaju)
    n += len(re.findall(r" {2,}", re.sub(r"\s*\n\s*", " ", p)))

    # nedostajuci razmak iza interpunkcije (kad slijedi slovo)
    for tok in p.split():
        if "@" in tok or "://" in tok or tok.lower().startswith("www."):
            continue
        for m in _RE_RAZMAK.finditer(tok):
            i = m.start()
            znak = tok[i]
            if znak == ".":
                if i > 0 and tok[i - 1] == ".":
                    continue  # tropoint
                if not tok[i + 1].isupper():
                    continue  # domena/fajl/skracenica, ne recenica
                if (
                    i > 0
                    and tok[i - 1].isalpha()
                    and (i < 2 or not tok[i - 2].isalnum())
                ):
                    continue  # inicijal ili d.o.o.
            n += 1

    # dijalog sa crticom (-) umjesto em-dash
    for linija in p.splitlines():
        if _RE_CRTICA.match(linija):
            n += 1

    # malo slovo iza kraja recenice
    for m in _RE_VELIKO.finditer(p):
        pre, znak = m.group(1), m.group(2)
        if znak == "." and (
            pre.isdigit() or len(pre) == 1 or pre.lower() in _SKRACENICE
        ):
            continue
        if p[m.end()].islower():
            n += 1
    return n


def _navodnici_greske(tekst: str) -> int:
    """Nespareni navodnici po tipu. ASCII " se ne mesa sa „ “."""
    n = 0
    # ASCII "..." — paran broj (svaki otvoreni ima zatvoreni)
    n += tekst.count('"') % 2
    # „...“ (njemacki) — otv mora biti == zatv
    n += abs(tekst.count("\u201e") - tekst.count("\u201c"))
    # ”...” (francuski, samo zatvoreni) — samo ako nema „
    if tekst.count("\u201e") == 0:
        n += abs(tekst.count("\u201c") - tekst.count("\u201d"))
    # «...» — paran
    n += abs(tekst.count("\u00ab") - tekst.count("\u00bb"))
    # ‘...’ — paran
    n += abs(tekst.count("\u2018") - tekst.count("\u2019"))
    return n


def _tipografija(pasusi: list) -> int:
    n = sum(_tipografija_pasus(p) for p in pasusi)
    return n + _navodnici_greske("\n".join(pasusi))


def compute_metrics(text: str, source: str | None = None) -> dict:
    """
    Racuna metrike za tekst (i opciono izvor).

    Returns:
        ekavizmi_per_1000, en_ostaci_per_1000, duplikati,
        ratio_source_target (None bez izvora), tipografija_greske, reci_ukupno
    """
    if not isinstance(text, str) or not text.strip():
        return _nule()

    cist = _cist(text)
    reci = len(_RE_RIJEC.findall(cist))
    if reci == 0:
        return _nule()

    ratio = None
    if isinstance(source, str) and source.strip():
        reci_src = len(_RE_RIJEC.findall(_cist(source)))
        if reci_src > 0:
            ratio = round(reci_src / reci, 4)

    pasusi = _pasusi(text)
    return {
        "ekavizmi_per_1000": round(_broji_ekavizme(cist) / reci * 1000, 2),
        "en_ostaci_per_1000": round(_detektuj_en_ostatke(cist) * 1000, 2),
        "duplikati": _broji_duplikate(pasusi),
        "ratio_source_target": ratio,
        "tipografija_greske": _tipografija(pasusi),
        "reci_ukupno": reci,
    }


# ─────────────────────────────────────────────────────────────
# Klasifikacija iz metrika (F3b)
# ─────────────────────────────────────────────────────────────

_METRIC_THRESHOLDS = {
    # {metrika: (OK_max, REVIEW_max)} — iznad REVIEW_max = REJECT
    "ekavizmi_per_1000": (2.0, 10.0),
    "en_ostaci_per_1000": (5.0, 25.0),
    "duplikati": (0, 2),
    "tipografija_greske": (3, 15),
}


def classify_metrics(metrics: dict) -> str:
    """
    Klasifikuje blok iz metrika (bez AI):
      TRUNCATED  — premalo reci (< 50), ne meri se
      REJECT     — bilo koja metrika preko REVIEW_max
      REVIEW     — 1-2 metrike preko OK, nijedna preko REVIEW
      OK         — sve u granicama
    """
    if not metrics:
        return "TRUNCATED"
    if metrics.get("reci_ukupno", 0) < 50:
        return "TRUNCATED"

    reject = False
    review = 0
    for key, (ok_max, review_max) in _METRIC_THRESHOLDS.items():
        v = metrics.get(key, 0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > review_max:
            reject = True
        elif v > ok_max:
            review += 1

    ratio = metrics.get("ratio_source_target")
    if isinstance(ratio, (int, float)):
        if ratio < 0.4 or ratio > 1.8:
            reject = True
        elif ratio < 0.5 or ratio > 1.5:
            review += 1

    if reject:
        return "REJECT"
    if review >= 1:
        return "REVIEW"
    return "OK"


# ═══════════════════════════════════════════════════════════════
# T3a — check_accuracy: determinističke provere tačnosti prevoda
# ═══════════════════════════════════════════════════════════════

_BROJ_RE = re.compile(r"\d+(?:[.,]\d+)*")
_KONTEKST_BROJ = 15  # znakova sa svake strane broja (~30 ukupno)


def _normalizuj_broj(broj: str) -> str:
    return broj.replace(",", ".")


def _nadji_brojeve(tekst: str) -> list:
    """Lista (normalizovan_broj, start, end) za svako pojavljivanje."""
    return [
        (_normalizuj_broj(m.group()), m.start(), m.end())
        for m in _BROJ_RE.finditer(tekst)
    ]


def _skup_str(brojevi) -> str:
    """Formatira Counter/set brojeva za ispis, sortirano numerički."""
    kljuc = lambda s: [int(p) for p in s.split(".")]
    return "{" + ", ".join(sorted(brojevi, key=kljuc)) + "}"


def _fragment_oko_broja(tekst: str, pozicije: list, visak: Counter) -> str:
    """Kontekst oko prvog broja koji je u višku; \"\" ako ga u tekstu nema."""
    for broj, start, end in pozicije:
        if visak[broj] > 0:
            od = max(0, start - _KONTEKST_BROJ)
            do = min(len(tekst), end + _KONTEKST_BROJ)
            return " ".join(tekst[od:do].split())
    return ""


def check_accuracy(hr_text: str, en_text: str, glossary: dict) -> dict:
    """
    Deterministička provera tačnosti prevoda za jedan blok.

    Vraća:
        {
          "score": 0-100,
          "issues": [
            {"code": "...", "severity": "greška"|"upozorenje",
             "detail": "...", "hr_fragment": "...", "en_fragment": "..."}
          ]
        }

    Provere:
      - brojevi_razlika (T3a) — brojevi u HR moraju biti isti kao u EN
      - rečenice_manjak (T3b)  — TODO
      - tagovi_razlika  (T3b)  — TODO
      - imena_nedostaju (T3c)  — TODO
      - en_ostaci       (T3c)  — TODO
      - duplikati       (T3d)  — TODO
      - prazni_pasus    (T3d)  — TODO
    """
    issues = []

    # --- brojevi_razlika ---
    hr_poz = _nadji_brojeve(hr_text)
    en_poz = _nadji_brojeve(en_text)
    hr_cnt = Counter(b for b, _, _ in hr_poz)
    en_cnt = Counter(b for b, _, _ in en_poz)
    if hr_cnt != en_cnt:
        hr_visak = hr_cnt - en_cnt
        en_visak = en_cnt - hr_cnt
        issues.append({
            "code": "brojevi_razlika",
            "severity": "greška",
            "detail": "U EN: %s, u HR: %s" % (
                _skup_str(en_visak), _skup_str(hr_visak)
            ),
            "hr_fragment": _fragment_oko_broja(hr_text, hr_poz, hr_visak),
            "en_fragment": _fragment_oko_broja(en_text, en_poz, en_visak),
        })

    # --- rečenice_manjak (T3b) ---
    hr_rec = [r for r in re.split(r'(?<=[.!?…])\s+', hr_text.strip()) if r.strip()]
    en_rec = [r for r in re.split(r'(?<=[.!?…])\s+', en_text.strip()) if r.strip()]
    if len(en_rec) > 0:
        odnos = len(hr_rec) / len(en_rec)
        if not (0.9 <= odnos <= 1.1):
            issues.append({
                "code": "rečenice_manjak",
                "severity": "upozorenje",
                "detail": "U EN: %d, u HR: %d (odnos %.2f)" % (
                    len(en_rec), len(hr_rec), odnos
                ),
                "hr_fragment": hr_rec[0][:60] if hr_rec else "",
                "en_fragment": en_rec[0][:60],
            })

    # --- tagovi_razlika (T3b) ---
    hr_em = len(re.findall(r'<em\b', hr_text, re.I))
    hr_br = len(re.findall(r'<br\b', hr_text, re.I))
    en_em = len(re.findall(r'<em\b', en_text, re.I))
    en_br = len(re.findall(r'<br\b', en_text, re.I))
    if (hr_em, hr_br) != (en_em, en_br):
        issues.append({
            "code": "tagovi_razlika",
            "severity": "upozorenje",
            "detail": "U EN: em=%d, br=%d; u HR: em=%d, br=%d" % (
                en_em, en_br, hr_em, hr_br
            ),
            "hr_fragment": "",
            "en_fragment": "",
        })

    # --- imena_nedostaju (T3c) ---
    if glossary:
        nedost_en = []
        nedost_hr = []
        en_frag = ""
        for en_ime, hr_ime in glossary.items():
            en_m = re.search(r'\b' + re.escape(en_ime) + r'\b', en_text)
            if not en_m:
                continue
            if hr_ime in hr_text or en_ime in hr_text:
                continue
            if not nedost_en:
                od = max(0, en_m.start() - _KONTEKST_BROJ)
                do = min(len(en_text), en_m.end() + _KONTEKST_BROJ)
                en_frag = " ".join(en_text[od:do].split())
            nedost_en.append(en_ime)
            nedost_hr.append(hr_ime)
        if nedost_en:
            issues.append({
                "code": "imena_nedostaju",
                "severity": "upozorenje",
                "detail": "U EN: %s, u HR nema: %s" % (
                    ", ".join(nedost_en[:5]) + (", ..." if len(nedost_en) > 5 else ""),
                    ", ".join(nedost_hr[:5]) + (", ..." if len(nedost_hr) > 5 else ""),
                ),
                "hr_fragment": "",
                "en_fragment": en_frag,
            })

    # --- en_ostaci (T3c) ---
    if len(hr_text) >= 100:
        en_stop = ["the", "and", "of", "is", "are", "was", "were", "you",
                   "they", "with", "from", "this", "that", "have", "has",
                   "had", "not", "but", "for", "what"]
        izuzeti = [
            (m.start(), m.end())
            for m in re.finditer(
                r'<em\b[^>]*>.*?</em>|<i\b[^>]*>.*?</i>|"[^"]*"',
                hr_text, re.S | re.I
            )
        ]
        ostaci = [
            m for m in re.finditer(r'\b(?:' + "|".join(en_stop) + r')\b', hr_text)
            if not any(s <= m.start() < e for s, e in izuzeti)
        ]
        if len(ostaci) >= 3:
            rijeci = list(dict.fromkeys(m.group() for m in ostaci))
            prvi = ostaci[0]
            od = max(0, prvi.start() - _KONTEKST_BROJ)
            do = min(len(hr_text), prvi.end() + _KONTEKST_BROJ)
            issues.append({
                "code": "en_ostaci",
                "severity": "upozorenje",
                "detail": "U HR tekstu %d EN stop-reči: %s" % (
                    len(ostaci),
                    ", ".join(rijeci[:5]) + (", ..." if len(rijeci) > 5 else ""),
                ),
                "hr_fragment": " ".join(hr_text[od:do].split()),
                "en_fragment": "",
            })

    # --- score (privremeno, do T3d) ---
    if any(i["severity"] == "greška" for i in issues):
        score = 40
    elif issues:
        score = 70
    else:
        score = 100

    return {"score": score, "issues": issues}
