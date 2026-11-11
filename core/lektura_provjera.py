"""P2.15: LEKTURA provjera izostavljenog. Ulaz i izlaz su HR. Po sadrzaju, ne po duljini:
ulazna recenica ciji sadrzajne rijeci (>=4 slova) nemaju dovoljno preklapanja ni s jednom izlaznom recenicom = izbacena."""
import re

from core.poravnanje import recenice

_PRAG = 0.4
_RIJ = re.compile(r"\w{4,}", re.U)


def _plain(t):
    t = re.sub(r"<!--.*?-->", " ", t or "", flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def _tok(s):
    return set(_RIJ.findall(s.lower()))


def izostavljeno(ulaz, izlaz):
    """-> {"ispao": broj izbacenih recenica (>=30 znakova), "udio": udio izbacenog teksta u ulazu, "primjer": str}"""
    a, b = _plain(ulaz), _plain(izlaz)
    if not a:
        return {"ispao": 0, "udio": 0.0, "primjer": ""}
    if not b:
        return {"ispao": 1, "udio": 1.0, "primjer": a[:60]}
    sa, sb = recenice(a), recenice(b)
    if not sa or not sb or len(sa) > 500 or len(sb) > 500:
        return {"ispao": 0, "udio": round(max(0.0, 1 - len(b) / len(a)), 3) if len(a) > 200 else 0.0, "primjer": ""}
    tb = [_tok(s) for s in sb]
    ispao = znakova = 0
    primjer = ""
    for s in sa:
        if len(s) < 30:
            continue
        ts = _tok(s)
        if len(ts) < 3:
            continue
        najbolje = max((len(ts & t) / len(ts) for t in tb if t), default=0.0)
        if najbolje < _PRAG:
            ispao += 1
            znakova += len(s)
            primjer = primjer or s[:60]
    return {"ispao": ispao, "udio": round(znakova / max(len(a), 1), 3), "primjer": primjer}
