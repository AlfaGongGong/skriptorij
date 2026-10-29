#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_compare.py — poredi HR i EN po poglavljima (word count ratio)."""
import argparse, re, sys, zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import unquote
from difflib import SequenceMatcher

DC = "{http://purl.org/dc/elements/1.1/}"

class P(HTMLParser):
    BLOCK = {"p","div","li","h1","h2","h3","h4","h5","h6","blockquote",
             "td","th","dt","dd","figcaption","caption","pre","section","article","tr"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.title, self.buf = [], "", []
        self.in_head, self.in_title, self.skip = False, False, 0
    def handle_starttag(self, tag, attrs):
        if tag == "head": self.in_head = True
        if tag == "title" and self.in_head: self.in_title = True
        if tag in ("script", "style"): self.skip += 1
        if tag in self.BLOCK: self.flush()
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip: self.skip -= 1
        if tag == "head": self.in_head = False
        if tag == "title": self.in_title = False
        if tag in self.BLOCK: self.flush()
    def handle_data(self, d):
        if self.skip: return
        if self.in_title: self.title += d
        elif not self.in_head: self.buf.append(d)
    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if t: self.text.append(t)

def local(t): return t.rsplit("}", 1)[-1]

def read_epub(path):
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    cont = ET.fromstring(z.read("META-INF/container.xml"))
    rootfile = next(e.get("full-path") for e in cont.iter() if local(e.tag) == "rootfile")
    opf = ET.fromstring(z.read(rootfile))
    base = rootfile.rsplit("/", 1)[0] if "/" in rootfile else ""
    def res(h):
        return base + "/" + unquote(h.split("#")[0]) if base else unquote(h.split("#")[0])
    manifest, spine = {}, []
    for e in opf.iter():
        ln = local(e.tag)
        if ln == "item":
            manifest[e.get("id","")] = (res(e.get("href","")), e.get("media-type",""), e.get("properties","") or "")
        elif ln == "itemref":
            spine.append(e.get("idref",""))
    chapters = []
    for idx, idref in enumerate(spine, 1):
        if idref not in manifest: continue
        href, mt, props = manifest[idref]
        if href not in names or "nav" in props.split(): continue
        if mt not in ("application/xhtml+xml", "text/html"): continue
        try:
            p = P()
            p.feed(z.read(href).decode("utf-8-sig", errors="replace"))
            p.close(); p.flush()
        except Exception:
            continue
        words = sum(len(t.split()) for t in p.text)
        title = p.title.strip() or next((t for t in p.text if 5 < len(t) < 100), href.rsplit("/",1)[-1])
        chapters.append({"idx": idx, "href": href, "title": title[:80], "words": words, "text": " ".join(p.text)})
    return chapters

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def match_chapter(hr_ch, en_chapters, used):
    # 1. fuzzy po naslovu
    hr_n = norm(hr_ch["title"])
    best, best_score = None, 0
    for en_ch in en_chapters:
        if en_ch["idx"] in used: continue
        en_n = norm(en_ch["title"])
        if not hr_n or not en_n: continue
        score = SequenceMatcher(None, hr_n, en_n).ratio()
        if score > best_score and score > 0.55:
            best, best_score = en_ch, score
    if best: return best
    # 2. fallback: po broju riječi (isti red veličine ±30%)
    hr_w = hr_ch["words"]
    if hr_w < 30: return None
    candidates = [e for e in en_chapters if e["idx"] not in used and 0.5 < hr_w / max(e["words"],1) < 2.0]
    if candidates:
        # najbliži po dužini
        return min(candidates, key=lambda e: abs(hr_w - e["words"]))
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hr")
    ap.add_argument("--source", required=True, help="EN original")
    ap.add_argument("--min-ratio", type=float, default=0.5, help="donji prag (default 0.5)")
    ap.add_argument("--max-ratio", type=float, default=2.0, help="gornji prag (default 2.0)")
    args = ap.parse_args()

    hr_chapters = read_epub(args.hr)
    en_chapters = read_epub(args.source)
    print(f"HR: {len(hr_chapters)} poglavlja")
    print(f"EN: {len(en_chapters)} poglavlja")
    print(f"Pragovi: ratio < {args.min_ratio} ili > {args.max_ratio}\n")

    used = set()
    flags = []
    matched = 0
    for hr in hr_chapters:
        en = match_chapter(hr, en_chapters, used)
        if en:
            matched += 1
            used.add(en["idx"])
        hr_w, en_w = hr["words"], en["words"] if en else 0
        if not en or en_w == 0:
            flags.append(("?", hr["idx"], hr["href"], hr["title"], hr_w, en_w, "?", "nema para"))
            continue
        ratio = hr_w / en_w
        if ratio < args.min_ratio or ratio > args.max_ratio:
            sev = "KRITIČNO" if ratio < 0.3 or ratio > 3.0 else "UPOZ"
            flags.append((sev, hr["idx"], hr["href"], hr["title"], hr_w, en_w, ratio, en["title"][:40]))

    print(f"Uparено: {matched}/{len(hr_chapters)}\n")
    if not flags:
        print("✅ Sva poglavlja imaju normalan omjer riječi.")
        return

    print(f"{len(flags)} poglavlja sa sumnjivim omjerom:\n")
    print(f"{'sev':<10} {'HR':>5} {'EN':>5} {'ratio':>6}  {'HR naslov':<40}  {'EN naslov':<40}")
    print("-"*120)
    for sev, idx, href, title, hr_w, en_w, ratio, en_title in flags:
        r = f"{ratio:.2f}" if isinstance(ratio, float) else "?"
        print(f"{sev:<10} {hr_w:>5} {en_w:>5} {r:>6}  {title[:40]:<40}  {en_title:<40}")

if __name__ == "__main__":
    main()
