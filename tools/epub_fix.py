#!/usr/bin/env python3
"""epub_fix: ispravke validnosti gotovog EPUB-a (cilj: EPUB 3).
Upotreba: epub_fix.py <ulaz.epub> <izlaz.epub>
Ulaz se ne dira. HTML se prepisuje samo ako je nesto promijenjeno.
"""
import re, sys, zipfile, posixpath, datetime, collections, difflib, os
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from bs4 import BeautifulSoup
from bs4.element import Tag

sys.setrecursionlimit(10000)
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
HTML_EXT = (".html", ".xhtml", ".htm")


def _reg(default):
    ET.register_namespace("", default)
    ET.register_namespace("dc", DC)
    ET.register_namespace("xsi", XSI)


def _xml(root):
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            + ET.tostring(root, encoding="unicode")).encode("utf-8")


def opf_putanja(z):
    c = ET.fromstring(z.read("META-INF/container.xml"))
    for e in c.iter():
        if e.tag.endswith("rootfile"):
            return e.get("full-path")
    raise SystemExit("nema rootfile u container.xml")


def fix_opf(data, opf_path, names, st):
    _reg(OPF)
    root = ET.fromstring(data)
    root.set("version", "3.0")
    q = lambda t: "{%s}%s" % (OPF, t)
    for el in root.iter():
        for k in [k for k in el.attrib if k.startswith("{%s}" % OPF)]:
            del el.attrib[k]
            st["opf_attr_skinut"] += 1
    md = root.find(q("metadata"))
    uid_id, uid = root.get("unique-identifier"), None
    for e in md.iter("{%s}identifier" % DC):
        if e.get("id") == uid_id:
            uid = (e.text or "").strip()
    if not any(m.get("property") == "dcterms:modified" for m in md.iter(q("meta"))):
        m = ET.SubElement(md, q("meta"), {"property": "dcterms:modified"})
        m.text = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        st["opf_modified_dodan"] += 1
    man = root.find(q("manifest"))
    odir = posixpath.dirname(opf_path)
    have = {posixpath.normpath(posixpath.join(odir, unquote(i.get("href", ""))))
            for i in man.iter(q("item"))}
    k = 0
    for n in names:
        if n.lower().endswith(".css") and n not in have:
            k += 1
            ET.SubElement(man, q("item"), {
                "id": "css-fix-%d" % k,
                "href": posixpath.relpath(n, odir or "."),
                "media-type": "text/css"})
            st["opf_css_dodan"] += 1
    for g in list(root.findall(q("guide"))):
        if len(g) == 0:
            root.remove(g)
            st["opf_guide_prazan"] += 1
    return _xml(root), uid


def fix_ncx(data, uid, st):
    _reg(NCX)
    root = ET.fromstring(data)
    q = lambda t: "{%s}%s" % (NCX, t)
    for i, np_ in enumerate(root.iter(q("navPoint")), 1):
        np_.set("playOrder", str(i))
        st["ncx_playorder"] += 1
    if uid:
        for m in root.iter(q("meta")):
            if m.get("name") == "dtb:uid":
                m.set("content", uid)
    return _xml(root)


def valid_id(s):
    t = re.sub(r"[^\w.\-]", "-", s)
    if not t or not (t[0].isalpha() or t[0] == "_"):
        t = "x" + t
    return t


def flatten_p(soup):
    n = 0
    while True:
        inner = None
        for p in soup.find_all("p"):
            if p.find_parent("p") is not None:
                inner = p
                break
        if inner is None:
            return n
        outer = inner.find_parent("p")
        tail = list(inner.next_siblings) if inner.parent is outer else []
        inner.extract()
        outer.insert_after(inner)
        if any(isinstance(x, Tag) or str(x).strip() for x in tail):
            newp = soup.new_tag("p")
            for x in tail:
                newp.append(x.extract())
            inner.insert_after(newp)
        n += 1


def div_u_p(soup):
    n = 0
    for d in soup.find_all("div"):
        par = d.parent.name if d.parent is not None else None
        if par in ("[document]", "body", "div", "section", "blockquote", "li",
                   "td", "th", "article", "aside", "figure", "dd", "main"):
            continue
        if not d.get_text().strip() and d.find("img") is None:
            d.decompose()
            n += 1
    return n


def fix_html(name, raw, names_set, st, idmap, dups):
    soup = BeautifulSoup(raw.decode("utf-8"), "html.parser")
    ch = False
    seen, first = set(), {}
    for t in soup.find_all(id=True):
        old = t["id"]
        new = valid_id(old)
        if new in seen:
            a_, b_ = first[new].strip(), t.get_text().strip()
            dups.append((name, new, a_ == b_,
                         difflib.SequenceMatcher(None, a_, b_).ratio(), a_[:70], b_[:70]))
            del t["id"]
            st["id_dup_skinut"] += 1
            ch = True
            continue
        seen.add(new)
        first[new] = t.get_text()
        if new != old:
            t["id"] = new
            idmap[(name, old)] = new
            st["id_nevazeci"] += 1
            ch = True
    n = flatten_p(soup)
    if n:
        st["p_u_p"] += n
        ch = True
    nd = div_u_p(soup)
    if nd:
        st["div_u_p"] += nd
        ch = True
    for im in soup.find_all("img"):
        if im.get("alt") is None:
            im["alt"] = ""
            st["img_alt"] += 1
            ch = True
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h.startswith("#") or SCHEME.match(h):
            continue
        p = unquote(h.split("#")[0])
        if not p:
            continue
        tgt = posixpath.normpath(posixpath.join(posixpath.dirname(name), p))
        if tgt not in names_set:
            a.unwrap()
            st["link_mrtav"] += 1
            ch = True
    return soup, ch


def main(src, dst):
    st = collections.Counter()
    z = zipfile.ZipFile(src)
    infos = z.infolist()
    junk = lambda n: ".bak" in n or n.startswith("overlay_backup")
    names = [i.filename for i in infos if not junk(i.filename)]
    st["smece_izbaceno"] = len(infos) - len(names)
    names_set = set(names)
    opf_path = opf_putanja(z)
    out = {}
    out[opf_path], uid = fix_opf(z.read(opf_path), opf_path, names, st)
    for n in names:
        if n.lower().endswith(".ncx"):
            out[n] = fix_ncx(z.read(n), uid, st)
    soups, idmap, dups, changed = {}, {}, [], set()
    for n in names:
        if n.lower().endswith(HTML_EXT):
            soup, ch = fix_html(n, z.read(n), names_set, st, idmap, dups)
            soups[n] = soup
            if ch:
                changed.add(n)
    if idmap:
        for n, soup in soups.items():
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if "#" not in h or SCHEME.match(h):
                    continue
                p, frag = h.split("#", 1)
                tgt = n if not p else posixpath.normpath(
                    posixpath.join(posixpath.dirname(n), unquote(p)))
                nv = idmap.get((tgt, frag))
                if nv:
                    a["href"] = p + "#" + nv
                    st["href_id"] += 1
                    changed.add(n)
    for n in changed:
        out[n] = str(soups[n]).encode("utf-8")
    with zipfile.ZipFile(dst, "w") as zo:
        for i in infos:
            if i.filename not in names_set:
                continue
            zi = zipfile.ZipInfo(i.filename, i.date_time)
            zi.compress_type = i.compress_type
            zi.external_attr = i.external_attr
            zo.writestr(zi, out.get(i.filename, z.read(i.filename)))
    ident = sum(1 for d in dups if d[2])
    print("epub_fix:", dict(st))
    print("html izmijenjeno: %d/%d | dup id: %d (identican tekst: %d)"
          % (len(changed), len(soups), len(dups), ident))
    for d in [d for d in dups if d[2]][:8]:
        print("  IDENTICAN dup:", d[0], d[1])
    try:
        os.makedirs(".logs", exist_ok=True)
        with open(".logs/epub_fix_dups.txt", "w", encoding="utf-8") as fh:
            for d in sorted(dups, key=lambda d: -d[3]):
                fh.write("%.2f\t%s\t%s\t%s\t%s\n" % (d[3], d[0], d[1], d[4], d[5]))
    except OSError as e:
        print("izvjestaj dup id nije zapisan:", e)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
