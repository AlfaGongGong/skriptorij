"""P2.15: classla (tokenize,pos) provjera stranog teksta u HR bloku. Lazy ucitavanje, thread-safe.
Strani/engleski tekst dobiva UPOS 'X'. Iskljuci s BOOKLYFI_CLASSLA=0."""
import os
import re
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NLP = None
_LOCK = threading.Lock()
_PAO = False


def _nlp():
    global _NLP, _PAO
    if _NLP is not None or _PAO:
        return _NLP
    with _LOCK:
        if _NLP is None and not _PAO:
            try:
                import classla
                _NLP = classla.Pipeline(
                    "hr", processors="tokenize,pos", use_gpu=False,
                    dir=os.path.join(_BASE, "data", "classla_resources"), logging_level="ERROR")
            except Exception:
                _PAO = True
    return _NLP


def analiza(html, max_znakova=6000):
    """-> {"rijeci","x","udio_x","sumnjive_rec","primjeri"} ili None ako classla nije dostupna."""
    nlp = _nlp()
    if nlp is None:
        return None
    t = re.sub(r"<!--.*?-->", " ", html or "", flags=re.S)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
    if len(t) < 20:
        return {"rijeci": 0, "x": 0, "udio_x": 0.0, "sumnjive_rec": 0, "primjeri": []}
    with _LOCK:
        doc = nlp(t[:max_znakova])
    ukupno = x = sumnjivih = 0
    primjeri = []
    for s in doc.sentences:
        w = [a for a in s.words if re.search(r"[A-Za-zČĆŽŠĐčćžšđ]", a.text)]
        if not w:
            continue
        nx = sum(1 for a in w if a.upos == "X")
        ukupno += len(w)
        x += nx
        if len(w) >= 4 and nx / len(w) >= 0.3:
            sumnjivih += 1
            if len(primjeri) < 2:
                primjeri.append(" ".join(a.text for a in s.words)[:80])
    return {"rijeci": ukupno, "x": x, "udio_x": round(x / max(ukupno, 1), 3),
            "sumnjive_rec": sumnjivih, "primjeri": primjeri}
