"""P2.17: ukloni odlomke na pocetku bloka koji su kopija kraja prethodnog bloka
(model je preveo kontekst 'prethodni odlomak' i ponovio ga u izlazu)."""
import difflib
import re

_HDR = re.compile(r"\A(\s*<!--\s*chunk_sha[^>]*-->\s*\n?)")
_UNIT = re.compile(r"(?s).*?(?:</p>|</div>|\\n\\n|\n\n)|.+\Z")
_MIN = 25


def _t(u):
    u = re.sub(r"<[^>]+>", " ", u)
    u = u.replace("\\n", " ").replace("&nbsp;", " ")
    return re.sub(r"[\W_]+", " ", u.lower()).strip()


def _isti(a, b):
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9


def skini_preklop(prev, cur, k=4, maxskip=3):
    """Vraca (novi_cur, broj_uklonjenih_odlomaka). Idempotentno; pri sumnji vraca cur nepromijenjen."""
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
    units = _UNIT.findall(body)
    if "".join(units) != body:
        return cur, 0
    kept, removed, skipped, scanning, last_removed = [], 0, 0, True, False
    for u in units:
        if scanning:
            t = _t(u)
            if t == "":
                if last_removed:
                    continue  # prazan odlomak odmah iza uklonjenog
                skipped += 1
                if skipped > maxskip:
                    scanning = False
            elif len(t) >= _MIN and any(_isti(t, p) for p in pu):
                removed += 1
                last_removed = True
                continue
            else:
                scanning = False
            if t == "":
                pass
            else:
                last_removed = False
        kept.append(u)
    if not removed:
        return cur, 0
    novo = "".join(kept)
    if len(_t(novo)) < 20:  # ne smije ostati prazan blok
        return cur, 0
    return hdr + novo, removed
