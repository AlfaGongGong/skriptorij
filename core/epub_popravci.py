"""epub_popravci: popravci nasljedjenih epubcheck gresaka na GOTOVOM EPUB-u (idempotentno).

1) @font-face blokovi ciji src url() NE POSTOJI u EPUB-u (npr. placeholder XXXXXXXXXXXXXXXX u
   page_styles.css) se uklanjaju (RSC-007). Blok s bar jednim postojecim url-om ostaje.
2) <guide><reference href="x.html#frag">: ako frag ne postoji u cilju, a postoji "x"+frag
   (epub_fix prefiksira id-ove koji pocinju brojkom) fragment se prepravlja; inace se skida (RSC-012).
CLI: python -m core.epub_popravci <ulaz.epub> [izlaz.epub]
"""
import os
import posixpath
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

_FONT_FACE = re.compile(r"@font-face\s*\{[^{}]*\}", re.I | re.S)
_URL = re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""", re.I)
_REF = re.compile(r'(<reference\b[^>]*?\bhref=")([^"#]*)#([^"]*)(")', re.I)
_HTML = (".html", ".xhtml", ".htm")


def _postoji(url, css_path, imena):
    u = unquote(url.strip()).split("#")[0].split("?")[0]
    if not u or u.startswith(("data:", "http:", "https:", "//")):
        return True
    if u.startswith("/"):
        kand = [posixpath.normpath(u.lstrip("/"))]
    else:
        kand = [posixpath.normpath(posixpath.join(posixpath.dirname(css_path), u)),
                posixpath.normpath(u)]
    return any(k in imena for k in kand)


def popravi_css(tekst, css_path, imena):
    """(novi_tekst, broj_uklonjenih_font_face_blokova)"""
    n = [0]

    def zam(m):
        urls = [x[1] for x in _URL.findall(m.group(0))]
        if urls and not any(_postoji(u, css_path, imena) for u in urls):
            n[0] += 1
            return ""
        return m.group(0)

    return _FONT_FACE.sub(zam, tekst), n[0]


def popravi_guide(opf, opf_path, imena, citaj):
    """(novi_opf, {"popravljen": n, "skinut": n}); citaj(ime) -> bytes."""
    st = {"popravljen": 0, "skinut": 0}
    kes = {}

    def ima(cilj, frag):
        if cilj not in kes:
            kes[cilj] = citaj(cilj).decode("utf-8", "ignore")
        return re.search(r'\b(?:id|name)="%s"' % re.escape(frag), kes[cilj]) is not None

    def zam(m):
        pre, href, frag, post = m.groups()
        if not frag:
            return m.group(0)
        cilj = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(href)))
        if cilj not in imena or not cilj.lower().endswith(_HTML):
            return m.group(0)
        if ima(cilj, frag):
            return m.group(0)
        if ima(cilj, "x" + frag):
            st["popravljen"] += 1
            return f"{pre}{href}#x{frag}{post}"
        st["skinut"] += 1
        return f"{pre}{href}{post}"

    return _REF.sub(zam, opf), st


def popravi(src, dst=None):
    """Popravlja EPUB; dst=None -> na mjestu (atomarno). Vraca statistiku."""
    src = Path(src)
    dst = Path(dst) if dst else src
    st = {"font_face_uklonjeno": 0, "guide_fragment_popravljen": 0, "guide_fragment_skinut": 0}
    with zipfile.ZipFile(src) as zi:
        infos = zi.infolist()
        imena = set(zi.namelist())
        nova = {}
        for n in sorted(imena):
            if n.lower().endswith(".css"):
                try:
                    t = zi.read(n).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                t2, k = popravi_css(t, n, imena)
                if k:
                    st["font_face_uklonjeno"] += k
                    nova[n] = t2.encode("utf-8")
            elif n.lower().endswith(".opf"):
                try:
                    t = zi.read(n).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                t2, g = popravi_guide(t, n, imena, zi.read)
                if g["popravljen"] or g["skinut"]:
                    st["guide_fragment_popravljen"] += g["popravljen"]
                    st["guide_fragment_skinut"] += g["skinut"]
                    nova[n] = t2.encode("utf-8")
        if not nova:
            if dst != src:
                shutil.copy2(src, dst)
            return st
        tmp = dst.with_name(dst.name + ".pop.tmp")
        redom = sorted(infos, key=lambda i: 0 if i.filename == "mimetype" else 1)
        with zipfile.ZipFile(tmp, "w") as zo:
            for i in redom:
                data = nova.get(i.filename, zi.read(i.filename))
                zo.writestr(i, data, compress_type=i.compress_type)
    os.replace(tmp, dst)
    return st


def _cli(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    if not a:
        print("Upotreba: python -m core.epub_popravci <ulaz.epub> [izlaz.epub]")
        return 1
    print(popravi(a[0], a[1] if len(a) > 1 else None))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
