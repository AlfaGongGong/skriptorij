#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_parallel.py — paralelni korpus EN↔HR iz EPUB parova.

Poravnava pasuse po fajlu (isto ime) DP algoritmom po dužini, filtrira
sumnjive parove, i vraća čiste (en, hr) parove spremne za few-shot.
"""
import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from html import unescape
from math import log
from pathlib import Path

RE_TAG = re.compile(r'<[^>]+>')
RE_P = re.compile(r'<p\b[^>]*>(.*?)</p>', re.I | re.S)
RE_WORD = re.compile(r'[^\W\d_]+')
RE_EN_STOP = re.compile(r'\b(?:the|and|of|is|are|was|were|you|they|with|from|this|that|have|has|had|not|but|for|what)\b', re.I)


def ucitaj_pasuse(epub_path, filename):
    """Vrati listu (idx, tekst) iz HTML fajla unutar EPUB-a."""
    with zipfile.ZipFile(epub_path) as z:
        try:
            t = z.read(filename).decode('utf-8', errors='replace')
        except KeyError:
            return []
    out = []
    for m in RE_P.finditer(t):
        raw = m.group(1)
        clean = unescape(RE_TAG.sub('', raw))
        clean = re.sub(r'\s+', ' ', clean).strip()
        if clean:
            out.append(clean)
    return out


def zajednicki_fajlovi(en_epub, hr_epub):
    """Vrati listu imena fajlova koja postoje u oba, sa >0 pasusa."""
    with zipfile.ZipFile(en_epub) as z:
        en_names = {n for n in z.namelist() if n.endswith(('.html', '.xhtml'))}
    with zipfile.ZipFile(hr_epub) as z:
        hr_names = {n for n in z.namelist() if n.endswith(('.html', '.xhtml'))}
    common = sorted(en_names & hr_names)
    return common


def align_dp(T, S):
    """DP alignment po dužini (Gale-Church-lite). T=EN, S=HR."""
    nT, nS = len(T), len(S)
    if nT == 0 or nS == 0:
        return []
    lt = [len(x) for x in T]
    ls = [len(x) for x in S]
    mu = log((sum(lt) + 1) / (sum(ls) + 1))
    GAP = 1.5
    band = max(25, int(0.25 * max(nT, nS)))

    def mcost(i, j):
        return max(abs(log((lt[i] + 1) / (ls[j] + 1)) - mu), 0.0)

    cost = [{} for _ in range(nT + 1)]
    back = [{} for _ in range(nT + 1)]
    cost[0][0] = 0.0
    for i in range(nT + 1):
        center = i * nS / nT
        lo = max(0, int(center) - band)
        hi = min(nS, int(center) + band)
        for j in range(lo, hi + 1):
            if i == 0 and j == 0:
                continue
            best, bp = None, None
            if i > 0 and j > 0:
                p = cost[i - 1].get(j - 1)
                if p is not None:
                    best, bp = p + mcost(i - 1, j - 1), (i - 1, j - 1)
            if i > 0:
                p = cost[i - 1].get(j)
                if p is not None and (best is None or p + GAP < best):
                    best, bp = p + GAP, (i - 1, j)
            if j > 0:
                p = cost[i].get(j - 1)
                if p is not None and (best is None or p + GAP < best):
                    best, bp = p + GAP, (i, j - 1)
            if best is not None and bp is not None:
                cost[i][j] = best
                back[i][j] = bp
    if nS not in back[nT]:
        return []
    pairs = []
    i, j = nT, nS
    while (i, j) != (0, 0):
        pi, pj = back[i][j]
        if pi == i - 1 and pj == j - 1:
            pairs.append((i - 1, j - 1))
        elif pi == i - 1:
            pairs.append((i - 1, None))
        else:
            pairs.append((None, j - 1))
        i, j = pi, pj
    pairs.reverse()
    return pairs


def je_dobar_par(en, hr):
    """Filter: da li je par čist za few-shot."""
    if len(en) < 100 or len(hr) < 100:
        return False
    if len(en) > 2000 or len(hr) > 2000:
        return False
    omjer = len(hr) / max(len(en), 1)
    if not (0.7 <= omjer <= 1.5):
        return False
    # Ne sme biti EN stop-reči u HR (osim u dijalogu koji je legit)
    en_in_hr = len(RE_EN_STOP.findall(hr))
    if en_in_hr > 3:
        return False
    # HR mora imati razmake i reči
    if len(RE_WORD.findall(hr)) < 15:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('en_epub', help='EN izvor')
    ap.add_argument('hr_epub', help='HR prevedeni')
    ap.add_argument('-o', '--out', default='data/few_shot_abercombie.json')
    ap.add_argument('--max-parova', type=int, default=1000)
    ap.add_argument('--min-znakova', type=int, default=100)
    args = ap.parse_args()

    common = zajednicki_fajlovi(args.en_epub, args.hr_epub)
    print(f'Zajednički fajlovi: {len(common)}')

    svi_parovi = []
    stats = {'fajlova_ok': 0, 'fajlova_skip': 0, 'parova_total': 0, 'parova_filter': 0}

    for fname in common:
        en_p = ucitaj_pasuse(args.en_epub, fname)
        hr_p = ucitaj_pasuse(args.hr_epub, fname)
        if not en_p or not hr_p:
            stats['fajlova_skip'] += 1
            continue
        alignment = align_dp(en_p, hr_p)
        if not alignment:
            stats['fajlova_skip'] += 1
            continue
        stats['fajlova_ok'] += 1
        for ti, si in alignment:
            if ti is None or si is None:
                continue
            stats['parova_total'] += 1
            en = en_p[ti]
            hr = hr_p[si]
            if not je_dobar_par(en, hr):
                stats['parova_filter'] += 1
                continue
            svi_parovi.append({'en': en[:500], 'hr': hr[:500], 'fajl': fname})

    print(f'Fajlova OK: {stats["fajlova_ok"]}, skip: {stats["fajlova_skip"]}')
    print(f'Ukupno parova: {stats["parova_total"]}, filtrirao: {stats["parova_filter"]}, čisto: {len(svi_parovi)}')

    # Ograniči na max_parova, raspoređeno
    if len(svi_parovi) > args.max_parova:
        step = len(svi_parovi) / args.max_parova
        svi_parovi = [svi_parovi[int(i * step)] for i in range(args.max_parova)]
        print(f'Sampling: {len(svi_parovi)} parova (raznovrsno)')

    out = {
        'izvor': 'TWP EN↔HR',
        'ukupno_parova': len(svi_parovi),
        'parovi': svi_parovi,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Sačuvano: {args.out} ({len(svi_parovi)} parova)')


if __name__ == '__main__':
    main()
