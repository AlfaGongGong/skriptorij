"""
epub/pdf_ulaz.py
================
PDF s tekstnim slojem -> EPUB (ulaz za postojeci pipeline).

Koristi pdftotext -layout (poppler), bez Python biblioteka.
Prepoznavanje (izmjereno na stvarnom PDF-u):
  - poglavlje: red "✦ N ✦" pa naslov velikim slovima u sredini;
  - odlomak: prvi red uvucen 1-11 razmaka, nastavak bez uvlake;
  - stranica s jednim kratkim naslovom velikim slovima = naslov dijela;
  - stranice bez teksta (ilustracije) se preskacu.
"""
from __future__ import annotations

import html
import logging
import re
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_CENTAR = 12
_PAR_MAX = 11
_BROJ_RE = re.compile(r"^[✦◆◇]\s*([IVXLCDM]{1,8})\s*[✦◆◇]$")
_ORNAMENT_RE = re.compile(r"^[\s✦◆◇•*·~–—-]{1,12}$")
_KAPA_RE = re.compile(
    r"^([„“\"’‘]*)((?:[A-ZČĆŠŽĐ]{2,}[,.]?\s+){1,5})(?=[a-zčćšžđ])"
)


def _uvlaka(red: str) -> int:
    return len(red) - len(red.lstrip())


def _caps_naslov(s: str) -> bool:
    s = s.strip()
    slova = [c for c in s if c.isalpha()]
    return (
        len(slova) >= 3
        and len(s) <= 45
        and all(c.isupper() for c in slova)
        and not s.endswith((".", ",", ";", ":", "!", "?", "”", "“", "’"))
    )


def _razmaknuta(s: str) -> bool:
    t = s.split()
    return len(t) >= 4 and all(len(x) <= 2 and x.isalpha() and x.isupper() for x in t)


def _naslov(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    t = s.split(" ")
    if len(t) >= 4 and all(len(x) <= 2 for x in t):
        s = "".join(t)
    s = re.sub(r"(?<=[A-ZČĆŠŽĐ])0(?=[A-ZČĆŠŽĐ]|$)", "O", s)
    s = s.lower()
    return s[:1].upper() + s[1:]


def _spoji(redovi: list[str]) -> str:
    out = ""
    for r in redovi:
        if not out:
            out = r
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and r[:1].islower():
            out = out[:-1] + r
        else:
            out += " " + r
    return out


def _kapa(t: str) -> str:
    m = _KAPA_RE.match(t)
    if not m:
        return t
    run = m.group(2).lower()
    return m.group(1) + run[:1].upper() + run[1:] + t[m.end():]


def stranice_iz_layout(tekst: str) -> list[str]:
    st = tekst.split("\f")
    if st and not st[-1].strip():
        st = st[:-1]
    return st


def parsiraj_sekcije(stranice: list[str]) -> list[dict]:
    redovi = []  # (uvlaka, tekst, stranica, prvi_na_stranici, rijetka_stranica)
    for pn, t in enumerate(stranice, 1):
        ls = t.splitlines()
        rijetka = sum(1 for l in ls if l.strip()) <= 3
        prvi = True
        for l in ls:
            s = l.strip()
            if not s:
                redovi.append((-1, "", pn, False, rijetka))
                continue
            ind = _uvlaka(l.expandtabs(4))
            if s.isdigit() and ind >= _CENTAR:
                continue  # broj stranice
            redovi.append((ind, s, pn, prvi, rijetka))
            prvi = False

    sekcije: list[dict] = []
    st = {"cur": None, "dio": None}
    par: list[str] = []
    cen: list[str] = []

    def tekuca() -> dict:
        if st["cur"] is None:
            st["cur"] = {"broj": None, "naslov": "Prolog", "dio": None, "odlomci": []}
            sekcije.append(st["cur"])
        return st["cur"]

    def isprazni_cen() -> None:
        if cen:
            tekuca()["odlomci"].append(("e", list(cen)))
            cen.clear()

    def isprazni() -> None:
        if par:
            tekuca()["odlomci"].append(("p", _spoji(par)))
            par.clear()
        isprazni_cen()

    def nova(broj, naslov) -> None:
        isprazni()
        st["cur"] = {"broj": broj, "naslov": naslov, "dio": st["dio"], "odlomci": []}
        st["dio"] = None
        sekcije.append(st["cur"])

    n = len(redovi)
    i = 0
    while i < n:
        ind, s, pn, prvi, rijetka = redovi[i]
        if ind == -1:
            isprazni_cen()
            i += 1
            continue
        m = _BROJ_RE.match(s)
        if m:
            j = i + 1
            while j < n and redovi[j][0] == -1:
                j += 1
            nas = []
            while (
                j < n
                and redovi[j][0] >= _CENTAR
                and _caps_naslov(redovi[j][1])
                and len(nas) < 3
            ):
                nas.append(redovi[j][1])
                j += 1
            nova(m.group(1), _naslov(" ".join(nas)) if nas else "")
            i = j
            continue
        centr = ind >= _CENTAR
        if centr and _razmaknuta(s):
            nova(None, _naslov(s))
            i += 1
            continue
        if prvi and _caps_naslov(s) and (centr or rijetka):
            if rijetka:
                isprazni()
                st["dio"] = _naslov(s)
            else:
                nova(None, _naslov(s))
            i += 1
            continue
        tekuca()
        if centr:
            if _ORNAMENT_RE.match(s):
                isprazni()
                tekuca()["odlomci"].append(("s", ""))
            else:
                if par:
                    isprazni()
                cen.append(s)
        else:
            isprazni_cen()
            if 1 <= ind <= _PAR_MAX:
                if par:
                    tekuca()["odlomci"].append(("p", _spoji(par)))
                    par.clear()
            par.append(s)
        i += 1
    isprazni()

    sekcije = [s for s in sekcije if s["odlomci"]]
    for s in sekcije:
        for k, (tip, v) in enumerate(s["odlomci"]):
            if tip == "p":
                s["odlomci"][k] = ("p", _kapa(v))
                break
    return sekcije


# ---------------------------------------------------------------------------
# EPUB
# ---------------------------------------------------------------------------

_CSS = (
    "body { font-family: serif; line-height: 1.4; }\n"
    "p { margin: 0 0 0.6em 0; text-align: justify; }\n"
    "h1, h2 { text-align: center; }\n"
    ".epigraf { text-align: center; font-style: italic; margin: 1em 2em; }\n"
    ".scena { text-align: center; margin: 1em 0; }\n"
)


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _naslov_sekcije(s: dict) -> str:
    if s["broj"] and s["naslov"]:
        return f'{s["broj"]}. {s["naslov"]}'
    return s["broj"] or s["naslov"] or "Poglavlje"


def _odlomak_html(tip: str, v) -> str:
    if tip == "p":
        return "<p>%s</p>" % _esc(v)
    if tip == "e":
        return '<p class="epigraf">%s</p>' % "<br/>".join(_esc(x) for x in v)
    return '<p class="scena">* * *</p>'


def _xhtml(s: dict, jezik: str) -> str:
    naslov = _esc(_naslov_sekcije(s))
    tijelo = []
    if s.get("dio"):
        tijelo.append('<h1 class="dio">%s</h1>' % _esc(s["dio"]))
    tijelo.append("<h2>%s</h2>" % naslov)
    tijelo.extend(_odlomak_html(t, v) for t, v in s["odlomci"])
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="%s">\n<head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
        "<title>%s</title>"
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n<body>\n%s\n</body>\n</html>\n'
        % (jezik, naslov, "\n".join(tijelo))
    )


def napravi_epub(sekcije, out_path, naslov, autor, jezik="sr", cover=None, seed=""):
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid5(uuid.NAMESPACE_URL, seed or naslov)
    imena = ["part%04d.xhtml" % (k + 1) for k in range(len(sekcije))]
    manifest = [
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
    ]
    if cover:
        manifest.append('<item id="cover-img" href="cover.jpg" media-type="image/jpeg"/>')
    manifest += [
        '<item id="p%d" href="%s" media-type="application/xhtml+xml"/>' % (k + 1, n)
        for k, n in enumerate(imena)
    ]
    spine = "".join('<itemref idref="p%d"/>' % (k + 1) for k in range(len(sekcije)))
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:opf="http://www.idpf.org/2007/opf">\n'
        "<dc:title>%s</dc:title>\n"
        '<dc:creator opf:role="aut">%s</dc:creator>\n'
        "<dc:language>%s</dc:language>\n"
        '<dc:identifier id="bookid">urn:uuid:%s</dc:identifier>\n%s'
        "</metadata>\n<manifest>\n%s\n</manifest>\n"
        '<spine toc="ncx">%s</spine>\n</package>\n'
        % (
            _esc(naslov),
            _esc(autor),
            jezik,
            uid,
            '<meta name="cover" content="cover-img"/>\n' if cover else "",
            "\n".join(manifest),
            spine,
        )
    )
    nav = "".join(
        '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
        '<content src="%s"/></navPoint>\n'
        % (k + 1, k + 1, _esc(_naslov_sekcije(s)), imena[k])
        for k, s in enumerate(sekcije)
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '<head><meta name="dtb:uid" content="urn:uuid:%s"/></head>\n'
        "<docTitle><text>%s</text></docTitle>\n<navMap>\n%s</navMap>\n</ncx>\n"
        % (uid, _esc(naslov), nav)
    )
    container = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n'
    )
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        d = zipfile.ZIP_DEFLATED
        z.writestr("META-INF/container.xml", container, compress_type=d)
        z.writestr("OEBPS/content.opf", opf, compress_type=d)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=d)
        z.writestr("OEBPS/style.css", _CSS, compress_type=d)
        if cover:
            z.writestr("OEBPS/cover.jpg", cover, compress_type=d)
        for k, s in enumerate(sekcije):
            z.writestr("OEBPS/" + imena[k], _xhtml(s, jezik), compress_type=d)
    tmp.replace(out)
    return out


# ---------------------------------------------------------------------------
# PDF -> EPUB
# ---------------------------------------------------------------------------


def _meta(pdf: Path) -> tuple[str, str]:
    dijelovi = [x.strip() for x in pdf.stem.split(" -- ")]
    if len(dijelovi) >= 2 and dijelovi[0] and dijelovi[1]:
        return dijelovi[0], dijelovi[1]
    naslov, autor = pdf.stem, "Nepoznat autor"
    try:
        info = subprocess.run(
            ["pdfinfo", str(pdf)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        ).stdout
        m = re.search(r"^Title:\s+(.+)$", info, re.M)
        if m and m.group(1).strip():
            naslov = m.group(1).strip()
        m = re.search(r"^Author:\s+(.+)$", info, re.M)
        if m and m.group(1).strip():
            autor = m.group(1).strip()
    except Exception:
        logger.warning("[pdf_ulaz] pdfinfo nije dostupan", exc_info=True)
    return naslov, autor


def _naslovnica(pdf: Path, prvi_tekst: str):
    if len(prvi_tekst.strip()) >= 50:
        return None
    try:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "cover"
            subprocess.run(
                ["pdftoppm", "-jpeg", "-r", "90", "-f", "1", "-l", "1",
                 "-singlefile", str(pdf), str(base)],
                capture_output=True, timeout=120, check=True,
            )
            f = Path(str(base) + ".jpg")
            return f.read_bytes() if f.exists() else None
    except Exception:
        logger.warning("[pdf_ulaz] naslovnica nije izvucena", exc_info=True)
        return None


def pdf_u_epub(pdf_path, out_path=None, log=None) -> Path:
    log = log or logger.info
    pdf = Path(pdf_path)
    out = Path(out_path) if out_path else pdf.with_suffix(".epub")
    if out.exists() and out.stat().st_size > 1000 and out.stat().st_mtime >= pdf.stat().st_mtime:
        log("PDF ulaz: koristim postojeci EPUB %s" % out)
        return out
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext nije instaliran (pkg install poppler)") from exc
    if r.returncode != 0:
        raise RuntimeError("pdftotext greska: %s" % r.stderr[:300])
    stranice = stranice_iz_layout(r.stdout)
    sekcije = parsiraj_sekcije(stranice)
    znakova = sum(len(v) if t == "p" else 0 for s in sekcije for t, v in s["odlomci"])
    if not sekcije or znakova < 2000:
        raise ValueError("PDF nema upotrebljiv tekstni sloj (sken? treba OCR)")
    naslov, autor = _meta(pdf)
    cover = _naslovnica(pdf, stranice[0] if stranice else "")
    log("PDF ulaz: %d stranica, %d poglavlja, %d znakova" % (len(stranice), len(sekcije), znakova))
    try:
        return napravi_epub(sekcije, out, naslov, autor, "sr", cover, seed=pdf.stem)
    except OSError:
        alt = Path(__file__).resolve().parent.parent / "data" / "pdf_epub" / (pdf.stem + ".epub")
        log("PDF ulaz: nema upisa uz PDF, pisem u %s" % alt)
        return napravi_epub(sekcije, alt, naslov, autor, "sr", cover, seed=pdf.stem)
