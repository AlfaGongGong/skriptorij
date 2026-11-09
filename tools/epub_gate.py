#!/usr/bin/env python3
"""
epub_gate.py - završna kapija nad finalnim EPUB-om (samo čita).
gate(path, forbid) -> (ok, nalazi)  |  nalaz = (razina, provjera, n, primjeri)
CLI: python3 tools/epub_gate.py <epub> [...] [--forbid Nail,Judge]   exit 0 = prošao, 1 = FAIL
"""
import argparse
import html
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote

_C = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_O = "{http://www.idpf.org/2007/opf}"
_D = "{http://purl.org/dc/elements/1.1/}"
_N = "{http://www.daisy.org/z3986/2005/ncx/}"

_FRONT = re.compile(
    r"halftitle|titlepage|otherbyauthor|copyright|dedication|contents|colophon|"
    r"abouttheauthor|otherrecommendations|acknowledg|^toc|^nav|^cover", re.I)
_BLK = re.compile(r"</(?:p|div|h[1-6]|li|blockquote|tr)>|<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_EN = {"the", "and", "was", "with", "that", "his", "her", "they", "were", "from",
       "have", "which", "said", "would", "there", "their", "been"}

_P = {
    ("FAIL", "dvostruki zarez ,,"): re.compile(r"(?<=[^\s(,]),{2,}"),
    ("FAIL", "zarez-razmak-tocka ', .'"): re.compile(r",[ \t]+\.(?!\.)"),
    ("FAIL", "siroce \u201d (razmak ispred, ne iza crte)"): re.compile(r"(?:^|(?<=[^\s\u2014\u2013-]\s))\u201d"),
    ("WARN", "razmak izmedju crte i \u201d"): re.compile(r"(?<=[\u2014\u2013-]\s)\u201d"),
    ("FAIL", "cirilica unutar rijeci"): re.compile(
        r"[A-Za-z\u00c0-\u024f][\u0400-\u04ff\u0590-\u06ff\u0e00-\u0e7f\u3040-\u30ff\u4e00-\u9fff]|[\u0400-\u04ff\u0590-\u06ff\u0e00-\u0e7f\u3040-\u30ff\u4e00-\u9fff][A-Za-z\u00c0-\u024f]"),
    ("FAIL", "AI/placeholder ostaci"): re.compile(
        r"NEPREVEDENO|___SAVED_|OVDJE_IDI|```|finalno_polirano|"
        r"(?:Lektorisani|Korigirani) tekst ovdje", re.I),
    ("FAIL", "HTML prikazan kao tekst"): re.compile(
        r"</?(?:p|em|i|strong|b|div|span|br|h[1-6])\b[^>]*>", re.I),
    ("WARN", "AI uvod na pocetku odlomka"): re.compile(r"^(?:Evo (?:prijevoda|rezultata)|Izvolite)\b"),
    ("WARN", 'ASCII navodnik "'): re.compile(r'"'),
}


def _lines(raw):
    m = re.search(r"<body\b.*</body>", raw, re.S | re.I)
    s = _DROP.sub("", m.group(0) if m else raw)
    s = _BLK.sub("\n", s)
    out = []
    for l in s.split("\n"):
        t = html.unescape(_TAG.sub("", l)).strip()
        if t:
            out.append(t)
    return out


def _ctx(ln, m):
    return ln[max(0, m.start() - 20):m.end() + 20]


def _fin(agg):
    rep = []
    for (lvl, chk), v in sorted(agg.items(), key=lambda kv: (kv[0][0] != "FAIL", kv[0][1])):
        ex = [(posixpath.basename(w) + (": " + e if e else "")) for w, e in v[:3]]
        rep.append((lvl, chk, len(v), ex))
    return (not any(r[0] == "FAIL" for r in rep)), rep


def _stil_provjera(path, opf, stil, add):
    """P4.3 (samo WARN): stil HR prijevoda naspram EN profila iz data/stil/<autor>.json.

    stil: dict (profil), str (putanja do JSON-a) ili None (trazi se po dc:creator).
    Bez profila ne radi nista.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from core import stil as _st
    except ImportError as e:
        print("[stil] core.stil nedostupan: %s" % e, file=sys.stderr)
        return
    if isinstance(stil, dict):
        en = stil
    else:
        if stil:
            p = Path(stil)
        else:
            cr = opf.find(".//" + _D + "creator")
            ime = (cr.text or "").strip() if cr is not None else ""
            if not ime:
                return
            p = root / "data" / "stil" / (_st.slug(ime) + ".json")
        if not p.is_file():
            return
        try:
            en = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print("[stil] ne mogu citati %s: %s" % (p, e), file=sys.stderr)
            return
    if not isinstance(en, dict) or en.get("jezik") != "en":
        return
    try:
        hr = _st.izmjeri(_st.izdvoji_odlomke(path), "hr")
    except Exception as e:  # noqa: BLE001 — kapija se ne smije srusiti zbog stila
        print("[stil] mjerenje HR nije uspjelo: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return
    for chk, ex in _st.usporedi(en, hr):
        add("WARN", chk, "stil", ex)


def gate(path, forbid=("Nail", "Judge"), stil=None):
    agg = {}

    def add(level, check, where, ex=""):
        agg.setdefault((level, check), []).append((where, ex))

    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        add("FAIL", "zip se ne moze otvoriti", str(path), str(e)[:80])
        return _fin(agg)
    with z:
        names = z.namelist()
        nset = set(names)
        bad = z.testzip()
        if bad:
            add("FAIL", "zip clan ostecen", bad)
        if "mimetype" not in nset:
            add("FAIL", "nema mimetype", "mimetype")
        else:
            if names[0] != "mimetype":
                add("WARN", "mimetype nije prvi u zipu", "mimetype")
            if z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                add("WARN", "mimetype komprimiran", "mimetype")
        try:
            root = ET.fromstring(z.read("META-INF/container.xml"))
            opf_path = root.find(".//" + _C + "rootfile").get("full-path")
            opf = ET.fromstring(z.read(opf_path))
        except Exception as e:
            add("FAIL", "container/OPF necitljiv", "META-INF", str(e)[:80])
            return _fin(agg)

        base = posixpath.dirname(opf_path)

        def res(h):
            return posixpath.normpath(posixpath.join(base, unquote(h.split("#")[0])))

        items = {i.get("id"): i for i in opf.iter(_O + "item")}
        for i in items.values():
            h = i.get("href", "")
            if h and not h.startswith(("http:", "https:")) and res(h) not in nset:
                add("FAIL", "manifest stavka nema fajl", h)
        spine = [r.get("idref") for r in opf.iter(_O + "itemref")]
        for r in spine:
            if r not in items:
                add("FAIL", "spine idref bez manifesta", str(r))
        t = opf.find(".//" + _D + "title")
        if t is None or not (t.text or "").strip():
            add("FAIL", "nema dc:title", opf_path)
        lg = opf.find(".//" + _D + "language")
        if lg is None or not (lg.text or "").strip():
            add("FAIL", "nema dc:language", opf_path)

        ncx = [i for i in items.values() if i.get("media-type") == "application/x-dtbncx+xml"]
        nav = [i for i in items.values() if "nav" in (i.get("properties") or "").split()]
        if not ncx and not nav:
            add("FAIL", "nema NCX ni nav", opf_path)
        for i in ncx:
            p = res(i.get("href", ""))
            if p in nset:
                try:
                    n = sum(1 for _ in ET.fromstring(z.read(p)).iter(_N + "navPoint"))
                except Exception as e:
                    add("FAIL", "NCX necitljiv", p, str(e)[:60])
                    continue
                if n == 0:
                    add("FAIL", "NCX bez poglavlja (navPoint=0)", p)
        for i in nav:
            p = res(i.get("href", ""))
            if p in nset and not re.search(rb"<a\b", z.read(p)):
                add("WARN", "nav bez linkova", p)

        rx_f = re.compile(r"\b(?:%s)" % "|".join(map(re.escape, forbid))) if forbid else None
        prev = ""
        n_docs = 0
        for idref in spine:
            it = items.get(idref)
            if it is None:
                continue
            p = res(it.get("href", ""))
            if p not in nset:
                continue
            data = z.read(p)
            try:
                ET.fromstring(data)
            except ET.ParseError as e:
                add("FAIL", "XHTML nije well-formed", p, str(e)[:60])
            raw = data.decode("utf-8", "replace")
            lines = _lines(raw)
            n_docs += 1
            front = bool(_FRONT.search(posixpath.basename(p)))
            if sum(map(len, lines)) < 20 and not re.search(r"<(?:img|svg|image)\b", raw, re.I):
                add("WARN", "prazna stranica", p)
            for ln in lines:
                for (lvl, chk), rx in _P.items():
                    for m in rx.finditer(ln):
                        add(lvl, chk, p, _ctx(ln, m))
                if rx_f and not front:
                    for m in rx_f.finditer(ln):
                        add("FAIL", "zabranjen pojam (%s)" % "/".join(forbid), p, _ctx(ln, m))
                if len(ln) > 40 and ln == prev:
                    add("FAIL", "uzastopni duplikat odlomka", p, ln[:50])
                nw = len(ln.split())
                if nw > 250:
                    add("WARN", "odlomak >250 rijeci", p, "%d r." % nw)
                prev = ln
            if not front:
                joined = " ".join(lines)
                allw = re.findall(r"\w+", joined)
                eng = sum(1 for w in re.findall(r"[A-Za-z']+", joined) if w.lower() in _EN)
                if len(allw) >= 50 and eng >= 5:
                    r = eng / len(allw)
                    if r >= 0.10:
                        add("FAIL", "neprevedeno (EN rijeci >=10%)", p, "%.0f%%" % (r * 100))
                    elif r >= 0.02:
                        add("WARN", "EN ostaci (2-10%)", p, "%.1f%%" % (r * 100))
        if n_docs == 0:
            add("FAIL", "spine bez dokumenata", opf_path)
        if stil is not False:
            _stil_provjera(path, opf, stil, add)
    return _fin(agg)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("epub", nargs="+")
    ap.add_argument("--forbid", default="Nail,Judge")
    ap.add_argument("--stil", default=None, help="putanja do data/stil/<autor>.json (inace po dc:creator)")
    ap.add_argument("--bez-stila", action="store_true", help="iskljuci P4.3 provjeru stila")
    a = ap.parse_args(argv)
    forbid = tuple(x for x in a.forbid.split(",") if x)
    rc = 0
    for p in a.epub:
        ok, rep = gate(p, forbid, stil=(False if a.bez_stila else a.stil))
        print("\n=== %s -> %s ===" % (p, "PROSAO" if ok else "PAO"))
        for lvl, chk, n, ex in rep:
            print("  %-4s %s x%d" % (lvl, chk, n))
            for e in ex:
                print("       " + e[:110])
        if not rep:
            print("  nema nalaza")
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
