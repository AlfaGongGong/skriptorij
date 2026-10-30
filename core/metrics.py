"""core/metrics.py — determinističke metrike tačnosti prevoda (T3a)."""
import re
from collections import Counter

_BROJ_RE = re.compile(r"\d+(?:[.,]\d+)*")
_KONTEKST = 15  # znakova sa svake strane broja (~30 ukupno)


def _normalizuj(broj: str) -> str:
    return broj.replace(",", ".")


def _nadji_brojeve(tekst: str) -> list:
    """Lista (normalizovan_broj, start, end) za svako pojavljivanje."""
    return [
        (_normalizuj(m.group()), m.start(), m.end())
        for m in _BROJ_RE.finditer(tekst)
    ]


def _skup_str(brojevi) -> str:
    kljuc = lambda s: [int(p) for p in s.split(".")]
    return "{" + ", ".join(sorted(brojevi, key=kljuc)) + "}"


def _fragment(tekst: str, pozicije: list, visak: Counter) -> str:
    """Kontekst oko prvog broja koji je u višku; "" ako ga u tekstu nema."""
    for broj, start, end in pozicije:
        if visak[broj] > 0:
            od = max(0, start - _KONTEKST)
            do = min(len(tekst), end + _KONTEKST)
            return " ".join(tekst[od:do].split())
    return ""


def check_accuracy(hr_text: str, en_text: str, glossary: dict) -> dict:
    """
    Vraća: {
        "score": 0-100,
        "issues": [
            {"code": "...", "severity": "greška"|"upozorenje",
             "detail": "...", "hr_fragment": "...", "en_fragment": "..."}
        ]
    }
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
            "hr_fragment": _fragment(hr_text, hr_poz, hr_visak),
            "en_fragment": _fragment(en_text, en_poz, en_visak),
        })

    # --- rečenice_manjak (T3b) ---
    # TODO T3b: broj rečenica u HR ne smije biti znatno manji nego u EN.
    pass

    # --- tagovi_razlika (T3b) ---
    # TODO T3b: HTML/XML tagovi u HR moraju odgovarati tagovima u EN.
    pass

    # --- imena_nedostaju (T3c) ---
    # TODO T3c: imena iz glossary moraju biti prisutna u HR.
    pass

    # --- en_ostaci (T3c) ---
    # TODO T3c: neprevedeni engleski ostaci u HR tekstu.
    pass

    # --- duplikati (T3d) ---
    # TODO T3d: ponovljeni identični pasusi/rečenice u HR.
    pass

    # --- prazni_pasus (T3d) ---
    # TODO T3d: prazan HR pasus uz neprazan EN.
    pass

    # --- score (privremeno, do T3d) ---
    if any(i["severity"] == "greška" for i in issues):
        score = 40
    elif issues:
        score = 70
    else:
        score = 100

    return {"score": score, "issues": issues}


# Test 1: isti brojevi, različit format zapisa
# check_accuracy("Bilo je 2,5 zlata.", "It was 2.5 gold.", {})
#   → score=100, issues=[]

# Test 2: različiti brojevi
# check_accuracy("Bilo je 3 zlata.", "It was 2.5 gold.", {})
#   → score=40, issues=[{code: "brojevi_razlika"}]

# Test 3: tačka u HR (isto kao EN)
# check_accuracy("Bilo je 2.5 zlata.", "It was 2.5 gold.", {})
#   → score=100, issues=[]
