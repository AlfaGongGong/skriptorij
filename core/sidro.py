"""P2.15: sidro za nalaze izostavljeno/dodano -> obicna zamjena (hr sidro -> novo) koju Zavrsi vec zna primijeniti."""
import difflib
import re

from core.poravnanje import poravnaj, recenice

KES = {}  # (blok, hr_sidro) -> {"novo": str|None, "tip": str}; puni /api/review/kartice


def _n(s):
    return re.sub(r"[\W_]+", " ", (s or "").lower()).strip()


def en_blok_za(en_t, k, frag):
    try:
        if not isinstance(en_t, dict):
            return ""
        v = en_t.get(k)
        if isinstance(v, (list, tuple)):
            v = " ".join(str(x) for x in v)
        if isinstance(v, str) and v:
            return v
        fn = _n(frag)
        if fn:
            for vv in en_t.values():
                if isinstance(vv, str) and fn in _n(vv):
                    return vv
    except Exception:
        pass
    return ""


def _najbolja(sents, frag):
    fn = _n(frag)
    best = (-1, 0.0)
    if not fn:
        return best
    for i, s in enumerate(sents):
        sn = _n(s)
        if not sn:
            continue
        if fn in sn:
            r = 1.0
        elif sn in fn and len(sn) >= 12:
            r = 0.9
        else:
            r = difflib.SequenceMatcher(None, fn, sn).ratio()
        if r > best[1]:
            best = (i, r)
    return best


def _ukloni(s, frag):
    if frag and frag in s:
        o = s.replace(frag, "", 1)
        o = re.sub(r"\s{2,}", " ", o)
        o = re.sub(r"\s+([,.;:!?])", r"\1", o).strip()
        return o
    return None


def sidro_za_nalaz(tip, en_frag, hr_frag, en_blok, hr_plain):
    """-> {"en", "hr", "novo"} ili None. hr je sidro koje se u .chk pojavljuje tocno jednom."""
    hr_plain = re.sub(r"\s+", " ", hr_plain or "")
    hr_s = recenice(hr_plain)
    if not hr_s:
        return None
    if tip == "dodano":
        fn = _n(hr_frag)
        if not fn:
            return None
        for i, s in enumerate(hr_s):
            sn = _n(s)
            if fn not in sn:
                continue
            if sn == fn or len(fn) > 0.8 * len(sn):
                if i == 0:
                    return None
                sid = hr_s[i - 1] + " " + s
                if hr_plain.count(sid) != 1:
                    return None
                return {"en": "(u izvorniku nema ovog dijela)", "hr": sid, "novo": hr_s[i - 1]}
            novo = _ukloni(s, hr_frag)
            if novo and novo != s and hr_plain.count(s) == 1:
                return {"en": "(u izvorniku nema ovog dijela)", "hr": s, "novo": novo}
            return None
        return None
    if tip == "izostavljeno":
        if not en_blok or not en_frag:
            return None
        if len(en_blok) > 2.5 * len(hr_plain) + 200:
            return None  # EN tekst nije na razini bloka
        en_s = recenice(en_blok)
        j, r = _najbolja(en_s, en_frag)
        if j < 0 or r < 0.6:
            return None
        beads = poravnaj(en_s, hr_s)
        if not beads:
            return None
        bi = next((x for x, ((e0, e1), _) in enumerate(beads) if e0 <= j < e1), None)
        if bi is None:
            return None
        (e0, e1), (h0, h1) = beads[bi]
        en_txt = " ".join(en_s[e0:e1])
        if h1 > h0:
            sid = " ".join(hr_s[h0:h1])
        else:
            sid = ""
            for x in range(bi - 1, -1, -1):
                (_, _), (a, b) = beads[x]
                if b > a:
                    sid = hr_s[b - 1]
                    break
            if not sid:
                for x in range(bi + 1, len(beads)):
                    (_, _), (a, b) = beads[x]
                    if b > a:
                        sid = hr_s[a]
                        break
        if len(sid) < 15 or len(sid) > 900 or hr_plain.count(sid) != 1:
            return None
        return {"en": en_txt, "hr": sid, "novo": None}
    return None


def provjeri_prijedlog(sidro, en, novo):
    """(ok, razlog): prijedlog mora sadrzavati vecinu rijeci sidra, ne smije biti kraci i bez EN/cirilice."""
    from core.gate_provjere import cir2lat
    from core.text_utils import _en_recenice
    if not novo or len(novo) < len(sidro) * 0.95:
        return False, "prekratko"
    a = set(_n(sidro).split())
    b = set(_n(novo).split())
    if a and len(a & b) / len(a) < 0.6:
        return False, "ne sadrzi sidro"
    if _en_recenice(novo) >= 1:
        return False, "engleski tekst"
    return True, ""


def sidro_za_blok(en_t, ck_dir, k, tip, en, hr, hr_plain):
    """Wrapper: nalazi EN odlomak (cijeli fajl ako imena odgovaraju, inace prozor oko fragmenta u bilo kojem EN fajlu)."""
    import glob
    import os
    hr_plain = re.sub(r"\s+", " ", hr_plain or "")
    if tip == "dodano":
        return sidro_za_nalaz(tip, en, hr, "", hr_plain)
    if not isinstance(en_t, dict) or not en_t or not en:
        return None
    fajl = k.split(".html_blok")[0] + ".html"
    if fajl in en_t:
        def _idx(p):
            m = re.search(r"_blok_(\d+)\.chk$", p)
            return int(m.group(1)) if m else 0
        parts = []
        for p in sorted(glob.glob(os.path.join(str(ck_dir), glob.escape(fajl) + "_blok_*.chk")), key=_idx):
            if p.endswith((".prevod.chk", ".lektura.chk")):
                continue
            raw = re.sub(r"<!--.*?-->", " ", open(p, encoding="utf-8", errors="ignore").read(), flags=re.S)
            parts.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))
        r = sidro_za_nalaz(tip, en, hr, en_t[fajl], " ".join(parts) if parts else hr_plain)
        if r and r.get("hr") and hr_plain.count(r["hr"]) == 1:
            return r
    words = re.findall(r"\w+", en)
    if len(words) < 3:
        return None
    rx = re.compile(r"\W+".join(re.escape(w) for w in words), re.I)
    for t in en_t.values():
        m = rx.search(t)
        if not m:
            continue
        W = int(0.7 * len(hr_plain)) + 200
        win = t[max(0, m.start() - W): m.end() + W]
        r = sidro_za_nalaz(tip, en, hr, win, hr_plain)
        if r and r.get("hr") and hr_plain.count(r["hr"]) == 1:
            return r
        return None
    return None
