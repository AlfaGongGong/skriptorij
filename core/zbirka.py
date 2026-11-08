"""core/zbirka.py: prepoznaje zbirke/antologije (vise autora), za koje profil jednog autora nema smisla.

je_zbirka(epub) -> (bool, razlog). Signali: >= 3 razlicita dc:creator; naslov ili ime fajla sadrzi
stories/tales/anthology/collection/best of; ime je na rucnoj listi data/zbirke.txt (jedan izraz po
retku, bez razlike velika/mala slova, trazi se u naslovu i imenu fajla; retci s # su komentari).
"""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_KORIJEN = Path(__file__).resolve().parent.parent
_RIJECI = re.compile(r"\b(stories|tales|anthology|collection|best of|years? best|year's best)\b", re.I)
_MIN_AUTORA = 3


def _lista():
    p = _KORIJEN / "data" / "zbirke.txt"
    if not p.is_file():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip().lower()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def _meta(epub):
    """(skup autora, naslov) iz prvog OPF-a; prazno ako nije citljivo."""
    autori, naslov = set(), ""
    with zipfile.ZipFile(epub) as z:
        opf = next((n for n in z.namelist() if n.lower().endswith(".opf")), None)
        if not opf:
            return autori, naslov
        root = ET.fromstring(z.read(opf))
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        t = (el.text or "").strip()
        if tag == "creator" and t:
            autori.add(t.lower())
        elif tag == "title" and t and not naslov:
            naslov = t
    return autori, naslov


def je_zbirka(epub):
    ime = Path(str(epub)).stem.replace("_", " ")
    try:
        autori, naslov = _meta(epub)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as e:
        autori, naslov = set(), ""
        print("[zbirka] metapodaci nisu citljivi: %r" % (e,))
    if len(autori) >= _MIN_AUTORA:
        return True, "%d autora u metapodacima" % len(autori)
    tekst = ("%s %s" % (naslov, ime)).lower()
    m = _RIJECI.search(tekst)
    if m:
        return True, "u naslovu/imenu: '%s'" % m.group(0)
    for izraz in _lista():
        if izraz in tekst:
            return True, "na listi data/zbirke.txt: '%s'" % izraz
    return False, ""
