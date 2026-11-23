# -*- coding: utf-8 -*-
"""epub/ocisti.py: P2.10/P2.11 - u gotovom EPUB-u uklanja <img> bez datoteke u paketu
(npr. indent.jpg iz Calibre izvora) i razvezuje <a href> kojima cilj (datoteka ili #id) ne postoji.
nav/toc dokument se ne dira. Piše atomarno; bez promjene ako nema nalaza.
API: ocisti_epub(putanja, dry=False) -> {"img": n, "link": m, "datoteka": k}"""
from __future__ import annotations

import os
import posixpath
import tempfile
import zipfile
from urllib.parse import unquote, urldefrag

from bs4 import BeautifulSoup

_HTML = (".xhtml", ".html", ".htm")
_VANJSKI = ("http:", "https:", "mailto:", "tel:", "data:", "javascript:", "ftp:")


def _cilj(naziv, ref):
    p = unquote(ref)
    return posixpath.normpath(posixpath.join(posixpath.dirname(naziv), p)) if p else naziv


_BLOK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "table",
         "blockquote", "pre", "hr", "address", "noscript", "ins", "del", "script", "style"}


def _blockquote_tekst_u_p(s):
    """XHTML 1.1: blockquote smije imati samo blokove. Goli tekst/inline se omota u <p>, br dijeli odlomke."""
    from bs4 import NavigableString
    n = 0
    for bq in s.find_all("blockquote"):
        djeca = list(bq.children)
        if not any((isinstance(c, NavigableString) and str(c).strip())
                   or (getattr(c, "name", None) and c.name not in _BLOK) for c in djeca):
            continue

        def flush(run, prije, bq=bq):
            nonlocal n
            if not any((isinstance(x, NavigableString) and str(x).strip()) or getattr(x, "name", None) for x in run):
                return
            p = s.new_tag("p")
            if prije is None:
                bq.append(p)
            else:
                prije.insert_before(p)
            for x in run:
                p.append(x.extract())
            n += 1

        run = []
        for c in djeca:
            ime = getattr(c, "name", None)
            if ime == "br":
                flush(run, c); run = []
                c.decompose()
            elif ime in _BLOK:
                flush(run, c); run = []
            else:
                run.append(c)
        flush(run, None)
    return n


def ocisti_epub(putanja, dry=False):
    putanja = str(putanja)
    rez = {"img": 0, "link": 0, "datoteka": 0}
    with zipfile.ZipFile(putanja) as z:
        info = z.infolist()
        podaci = {i.filename: z.read(i.filename) for i in info}
    donji = {n.lower(): n for n in podaci}
    soupovi, ids = {}, {}
    for n, b in podaci.items():
        if n.lower().endswith(_HTML):
            s = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
            soupovi[n] = s
            ids[n] = {str(e.get(a)) for e in s.find_all(True) for a in ("id", "name") if e.get(a)}
    izmijenjeno = {}
    for n, s in soupovi.items():
        nav = posixpath.basename(n).lower() in ("nav.xhtml", "toc.xhtml") or s.find(attrs={"epub:type": "toc"}) is not None
        ch = False
        # EPUB 2 / XHTML 1.1: br ne smije biti izravno u body (RSC-005); izvor ga ima izmedju <p>
        for _b in list(s.find_all("br")):
            if _b.parent is not None and _b.parent.name in ("body", "html"):
                _b.decompose()
                ch = True
        if _blockquote_tekst_u_p(s):
            ch = True
        for im in list(s.find_all("img")):
            src = (im.get("src") or "").strip()
            if not src or src.lower().startswith(_VANJSKI):
                continue
            if _cilj(n, src.split("?")[0].split("#")[0]).lower() not in donji:
                im.decompose()
                rez["img"] += 1
                ch = True
        if not nav:
            for a in list(s.find_all("a", href=True)):
                href = a["href"].strip()
                if not href or href.lower().startswith(_VANJSKI):
                    continue
                p, frag = urldefrag(href)
                st = donji.get(_cilj(n, p).lower())
                mrtav = st is None
                if not mrtav and frag and st in ids and unquote(frag) not in ids[st]:
                    mrtav = True
                if mrtav:
                    a.unwrap()
                    rez["link"] += 1
                    ch = True
        if ch:
            izmijenjeno[n] = s
    rez["datoteka"] = len(izmijenjeno)
    if dry or not izmijenjeno:
        return rez
    nova = {}
    for n, s in izmijenjeno.items():
        orig = podaci[n].decode("utf-8", "replace")
        t = str(s)
        if orig.lstrip().startswith("<?xml") and not t.lstrip().startswith("<?xml"):
            t = orig[: orig.find("?>") + 2] + "\n" + t
        nova[n] = t.encode("utf-8")
    fd, tmp = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(putanja) or ".")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w") as zo:
            for i in info:
                zo.writestr(i, nova.get(i.filename, podaci[i.filename]), compress_type=i.compress_type)
        os.replace(tmp, putanja)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return rez
