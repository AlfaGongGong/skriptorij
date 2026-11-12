"""P2.17 v2: ukloni odlomke (i ponovljene prve recenice odlomka) na pocetku bloka koji su
kopija kraja prethodnog bloka (model je preveo kontekst 'prethodni odlomak' i ponovio ga)."""
import difflib
import re

_HDR = re.compile(r"\A(\s*<!--\s*chunk_sha[^>]*-->\s*\n?)")
_UNIT = re.compile(r"(?s).*?(?:</p>|</div>|\\n\\n|\n\n)|.+\Z")
_TOK = re.compile(r"<[^>]+>|[^\s<]+|\s+")
_SENT_END = re.compile(r"[.!?…]+[\"”»’')\]]*$")
_MIN = 25
_MINW = 6


def _t(u):
    u = re.sub(r"<[^>]+>", " ", u)
    u = u.replace("\\n", " ").replace("&nbsp;", " ")
    return re.sub(r"[\W_]+", " ", u.lower()).strip()


def _isti(a, b):
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9


def _prefix_strip(unit, pw):
    """Ako odlomak pocinje istim recenicama kao neki prethodni odlomak (pw = liste normaliziranih rijeci),
    skini te recenice (tagovi ostaju). Vraca (novi_unit, broj_rijeci) ili (unit, 0)."""
    toks = _TOK.findall(unit)
    if "".join(toks) != unit:
        return unit, 0
    flat = []  # (indeks tokena, rijec)
    for i, t in enumerate(toks):
        if t.startswith("<") or t.isspace():
            continue
        for x in re.sub(r"[\W_]+", " ", t.replace("\\n", " ").lower()).split():
            flat.append((i, x))
    cw = [x for _, x in flat]
    if not cw:
        return unit, 0
    best_cand, best_n = -1, 0
    for words in pw:
        n = 0
        while n < len(cw) and n < len(words) and cw[n] == words[n]:
            n += 1
        if n < _MINW:
            continue
        if n == len(cw):  # cijeli odlomak je pocetak prethodnog -> ukloni cijeli
            return "", n
        lasttok = flat[n - 1][0]
        cand = -1
        for i in range(lasttok, -1, -1):
            t = toks[i]
            if t.startswith("<") or t.isspace():
                continue
            if _SENT_END.search(t.replace("\\n", "")):
                cand = i
                break
        if cand < 0:
            continue
        cons = sum(1 for i, _ in flat if i <= cand)
        if cons >= _MINW and cons > best_n:
            best_cand, best_n = cand, cons
    if best_cand < 0:
        return unit, 0
    out = []
    for i, t in enumerate(toks):
        if i <= best_cand and not t.startswith("<"):
            continue  # tekst i razmaci prefiksa; tagovi ostaju
        out.append(t)
    return "".join(out).lstrip(), best_n


def skini_preklop(prev, cur, k=15, maxskip=3):
    """Vraca (novi_cur, broj_uklonjenih_dijelova). Idempotentno; pri sumnji vraca cur nepromijenjen."""
    if not isinstance(prev, str) or not isinstance(cur, str):
        return cur, 0
    m = _HDR.match(cur)
    hdr = m.group(1) if m else ""
    body = cur[len(hdr):]
    pm = _HDR.match(prev)
    pbody = prev[len(pm.group(1)):] if pm else prev
    pu = [t for t in (_t(u) for u in _UNIT.findall(pbody)) if len(t) >= _MIN][-k:]
    if not pu:
        return cur, 0
    pw = [t.split() for t in pu]
    units = _UNIT.findall(body)
    if "".join(units) != body:
        return cur, 0
    kept, removed, skipped, scanning, last_removed = [], 0, 0, True, False
    for u in units:
        if not scanning:
            kept.append(u)
            continue
        t = _t(u)
        if t == "":
            if last_removed:
                continue
            skipped += 1
            if skipped > maxskip:
                scanning = False
            kept.append(u)
            continue
        last_removed = False
        if len(t) >= _MIN and any(_isti(t, p) for p in pu):
            removed += 1
            last_removed = True
            continue
        nu, nr = _prefix_strip(u, pw)
        if nr:
            removed += 1
            if _t(nu):
                kept.append(nu)
                scanning = False
            else:
                last_removed = True
            continue
        scanning = False
        kept.append(u)
    if not removed:
        return cur, 0
    novo = "".join(kept)
    if len(_t(novo)) < 20:
        return cur, 0
    return hdr + novo, removed
