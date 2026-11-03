"""lint_hr: deterministicki popravci i oznake izlaza prijevoda EN->HR.

Radi samo nad tekstom izvan HTML tagova. Bez AI-ja. Idempotentno.
lint_blok(html) -> (novi_html, {"fix": {pravilo: n}, "flag": {pravilo: n}})
fix  = sigurni popravci (mijenjaju tekst)
flag = samo oznaka, tekst se ne mijenja
"""
import re

OP, CL = "\u201e", "\u201d"
_TAGS = re.compile(r"(<[^>]+>)")
_PAR = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
_WORD = re.compile(r"\w+")
_CYR = {0x430: "a", 0x435: "e", 0x43E: "o", 0x440: "p", 0x441: "c",
        0x445: "x", 0x443: "y", 0x456: "i"}
_LAT = re.compile(r"[A-Za-z\u00c0-\u024f]")
_CYRL = re.compile(r"[\u0400-\u04ff]")

_R_DBL = re.compile(r"(?<=[^\s(,]),{2,}")
_R_HYP = re.compile(r"(?<=\w)" + OP + r"(?=-\w)")
_R_CLO = re.compile(r"(?<=\S)" + OP + r"(?=\s|[,.;:!?)\u2014])")
_F_ZT = re.compile(r",[ \t]+\.(?!\.)")
_F_POSS = re.compile("\\b[A-Z][A-Za-z]+[\u2019'" + OP + "]s\\b")


def _cyr_u_rijeci(m):
    w = m.group(0)
    return w.translate(_CYR) if _LAT.search(w) and _CYRL.search(w) else w


def _zbroji(d, k, n=1):
    if n:
        d[k] = d.get(k, 0) + n


def _sub_n(rx, rep, s):
    n = 0

    def f(m):
        nonlocal n
        r = rep(m) if callable(rep) else rep
        if r != m.group(0):
            n += 1
        return r

    return rx.sub(f, s), n


def lint_blok(html):
    fix, flag = {}, {}
    if not html:
        return html, {"fix": fix, "flag": flag}
    parts = _TAGS.split(html)
    for i in range(0, len(parts), 2):
        s = parts[i]
        s, n = _sub_n(_R_DBL, ",", s)
        _zbroji(fix, "dvostruki_zarez", n)
        s, n = _sub_n(_R_HYP, "", s)
        _zbroji(fix, "navodnik_u_imenu", n)
        s, n = _sub_n(_R_CLO, CL, s)
        _zbroji(fix, "otvarajuci_umjesto_zatvarajuceg", n)
        if (s.endswith(OP) and len(s) > 1 and not s[-2].isspace()
                and i + 1 < len(parts) and parts[i + 1].startswith("</")):
            s = s[:-1] + CL
            _zbroji(fix, "otvarajuci_umjesto_zatvarajuceg")
        s, n = _sub_n(_WORD, _cyr_u_rijeci, s)
        _zbroji(fix, "cirilica_u_latinici", n)
        parts[i] = s
        _zbroji(flag, "zarez_tocka_ispalo_nesto", len(_F_ZT.findall(s)))
        _zbroji(flag, "engleski_posvojni_oblik", len(_F_POSS.findall(s)))
    out = "".join(parts)
    ps = [_TAGS.sub("", p).strip() for p in _PAR.findall(out)]
    for j, p in enumerate(ps):
        if p.count(OP) > p.count(CL) and not (j + 1 < len(ps) and ps[j + 1].startswith(OP)):
            _zbroji(flag, "navodnik_bez_zatvaraca")
    return out, {"fix": fix, "flag": flag}
