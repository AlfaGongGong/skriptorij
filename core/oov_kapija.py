"""P2.18: kapija za engleski tekst i nepoznate rijeci u HR bloku (bez AI poziva)."""
import re
import shutil
import subprocess

EN_PRAG = 0.12
OOV_PRAG = 40.0
MIN_RIJECI = 40

_TAG = re.compile(r"<!--.*?-->|<[^>]+>", re.S)
_RIJEC = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)
_EN = frozenset(
    "the and of was he his she her that with for had you said not but they from this "
    "have were are him them then there what when who which would could into been their "
    "your will than".split()
)


def ocisti(t):
    return _TAG.sub(" ", t or "")


def rijeci(t):
    return _RIJEC.findall(ocisti(t))


def en_udio(t):
    w = [x.lower() for x in rijeci(t)]
    if len(w) < MIN_RIJECI:
        return 0.0
    return sum(1 for x in w if x in _EN) / len(w)


def _nepoznate(uniq):
    if not uniq or not shutil.which("hunspell"):
        return set()
    try:
        o = subprocess.run(
            ["hunspell", "-d", "hr_HR", "-l"],
            input="\n".join(uniq), capture_output=True, text=True, timeout=30,
        )
        if o.returncode != 0:
            return set()
        return set(o.stdout.split("\n")) - {""}
    except Exception:
        return set()


def oov_rate(t):
    toks = rijeci(t)
    if len(toks) < MIN_RIJECI:
        return 0.0
    uniq = sorted({x.lower() for x in toks if len(x) >= 3 and not x[0].isupper()})
    unk = _nepoznate(uniq)
    if not unk:
        return 0.0
    n = sum(1 for x in toks if x.lower() in unk and not x[0].isupper())
    return n / len(toks) * 1000.0


def provjeri(t):
    """Vraca dict: odbij (bool), razlog, en, oov."""
    r = {"odbij": False, "razlog": "", "en": 0.0, "oov": 0.0}
    if not t or "NEPREVEDENO" in t:
        return r
    r["en"] = en_udio(t)
    if r["en"] >= EN_PRAG:
        r["odbij"] = True
        r["razlog"] = "engleski tekst (EN udio %.0f%%)" % (r["en"] * 100)
        return r
    r["oov"] = oov_rate(t)
    if r["oov"] >= OOV_PRAG:
        r["odbij"] = True
        r["razlog"] = "nepoznate rijeci (%.0f/1000)" % r["oov"]
    return r


# P2.23 glosar guard: EN termin iz glosara ostao u HR tekstu (npr. "Beauty", "Beautyin")
_GL_RX = re.compile(r"^-\s+(.+?)\s+->\s+(.+?)(?:\s+\(spoji sa:[^)]*\))?\s+\[[^\]]*\]\s*$")


def glosar_neprevedeno(rel_glosar, tekst):
    """Vraca listu EN termina iz relevantnog glosara ('- EN -> HR [kat]') koji su ostali u tekstu
    neprevedeni. Preskace termine kod kojih je HR isti kao EN i kratke (<4 slova)."""
    if not rel_glosar or not tekst:
        return []
    plain = _TAG.sub(" ", tekst)
    res = []
    for linija in str(rel_glosar).split("\n"):
        m = _GL_RX.match(linija.strip())
        if not m:
            continue
        en, hr = m.group(1).strip(), m.group(2).strip()
        if len(en) < 4 or en.lower() == hr.lower() or en.lower() in hr.lower():
            continue
        oblici = {en}
        if en.islower():
            oblici.add(en.capitalize())
        suf = r"\w{0,3}" if len(en) >= 5 else ""
        for o in oblici:
            if re.search(r"(?<!\w)" + re.escape(o) + suf + r"(?!\w)", plain):
                res.append(en)
                break
    return res
