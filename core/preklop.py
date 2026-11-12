"""P2.17 v3: ukloni preklop na pocetku bloka (echo konteksta prethodnog bloka):
sidro (odlomci do zadnjeg koji je kopija kraja prethodnog bloka), spojeni odlomci, ponovljene prve recenice."""
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
    if a == b:
        return True
    if not a or not b:
        return False
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < 0.9 or sm.quick_ratio() < 0.9:
        return False
    return sm.ratio() >= 0.9


def _prefix_strip(unit, pw):
    toks = _TOK.findall(unit)
    if "".join(toks) != unit:
        return unit, 0
    flat = []
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
        if n == len(cw):
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
            continue
        out.append(t)
    return "".join(out).lstrip(), best_n


def _anchor(units, pu, maxu=30):
    """Indeks zadnjeg odlomka u cur (prvih maxu nepraznih) koji je kopija odlomka iz pu, uz rastuci redoslijed.
    Svi odlomci prije njega moraju biti echo (kontekst uvijek dolazi prije novog teksta). -1 ako nema."""
    matches, seen, first_nb = [], 0, None
    for ui, u in enumerate(units):
        t = _t(u)
        if not t:
            continue
        if first_nb is None:
            first_nb = ui
        seen += 1
        if seen > maxu:
            break
        if len(t) < _MIN:
            continue
        hit = pu.index(t) if t in pu else next((pi for pi, p in enumerate(pu) if _isti(t, p)), None)
        if hit is not None:
            matches.append((ui, hit))
    if not matches:
        return -1
    chain = [matches[0]]
    for m in matches[1:]:
        if m[1] > chain[-1][1]:
            chain.append(m)
    if len(chain) >= 2 or chain[0][0] == first_nb:
        return chain[-1][0]
    return -1


def skini_preklop(prev, cur, k=25, maxskip=3):
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
    removed = 0
    j = _anchor(units, pu)
    if j >= 0:
        removed += sum(1 for u in units[:j + 1] if _t(u))
        units = units[j + 1:]
        while units and not _t(units[0]):
            units = units[1:]
    kept, skipped, scanning, last_removed = [], 0, True, j >= 0
    for u in units:
        if not scanning:
            kept.append(u)
            continue
        cu = u
        while True:
            t = _t(cu)
            if t == "":
                break
            if len(t) >= _MIN and any(_isti(t, p) for p in pu):
                removed += 1
                cu = None
                break
            nu, nr = _prefix_strip(cu, pw)
            if nr:
                removed += 1
                if not _t(nu):
                    cu = None
                    break
                cu = nu
                continue
            break
        if cu is None:
            last_removed = True
            continue
        if _t(cu) == "":
            if last_removed:
                continue
            skipped += 1
            if skipped > maxskip:
                scanning = False
            kept.append(cu)
            continue
        scanning = False
        kept.append(cu)
    if not removed:
        return cur, 0
    novo = "".join(kept)
    if len(_t(novo)) < 20:
        return cur, 0
    return hdr + novo, removed
