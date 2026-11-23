#!/usr/bin/env python3
"""apply_overlay v2.
Upotreba: apply_overlay.py <checkpoint_dir> <overlay_json> [--strict] [--dry]
Unos: {"fajl","novo", ("staro" | "od"+"do"), "blok"?, "id"?}
 - staro: mora postojati TOCNO 1x u fajlu; "od"/"do": raspon, svaki sidro 1x.
 - bez "blok": trazi se u svim blokovima, mora pogoditi tocno 1 fajl.
 - vec primijenjeno (novo vec u fajlu) -> preskace (idempotentno).
 - .prevod.chk i .lektura.chk se nikad ne diraju.
"""
import sys, json, os
from pathlib import Path


def _kandidati(ck, fajl, blok):
    if blok is not None:
        p = ck / f"{fajl}_blok_{blok}.chk"
        return [p] if p.exists() else []
    return [p for p in sorted(ck.glob(f"{fajl}_blok_*.chk"))
            if not p.name.endswith((".prevod.chk", ".lektura.chk"))]


def _nadji(t, isp):
    """(start, end) | None (nema) | 'dup' (nejednoznacno)"""
    if "od" in isp:
        od, do = isp["od"], isp["do"]
        n = t.count(od)
        if n == 0:
            return None
        if n > 1:
            return "dup"
        i = t.find(od)
        j = t.find(do, i + len(od))
        if j < 0:
            return None
        if t.count(do) != 1:
            return "dup"
        return (i, j + len(do))
    staro = isp["staro"]
    n = t.count(staro)
    if n == 0:
        return None
    if n > 1:
        return "dup"
    i = t.find(staro)
    return (i, i + len(staro))


def primijeni(ck, ispravke, strict=False, bdir=None, dry=False, log=print):
    ck = Path(ck)
    st = {"ok": 0, "vec": 0, "fail": 0}
    for n, isp in enumerate(ispravke, 1):
        oid = isp.get("id") or f"#{n}"
        fajl, novo = isp.get("fajl"), isp.get("novo")
        ima = bool(isp.get("staro")) or ("od" in isp and "do" in isp)
        if not fajl or novo is None or not ima:
            log(f"  SKIP {oid}: nepotpun unos")
            st["fail"] += 1
            continue
        cands = _kandidati(ck, fajl, isp.get("blok"))
        if not cands:
            log(f"  WARN {oid}: nema .chk za {fajl} blok={isp.get('blok')}")
            st["fail"] += 1
            continue
        hit, applied, dup = [], [], []
        for p in cands:
            t = p.read_bytes().decode("utf-8")
            r = _nadji(t, isp)
            if r == "dup":
                dup.append(p)
            elif r is None:
                if (novo and novo in t) or (isp.get("brisi") and isp.get("blok") is not None):
                    applied.append(p)
            else:
                hit.append((p, t, r))
        if dup:
            log(f"  FAIL {oid}: nejednoznacno u {[p.name for p in dup]}")
            st["fail"] += 1
        elif len(hit) > 1:
            log(f"  FAIL {oid}: pogodak u vise fajlova {[h[0].name for h in hit]}")
            st["fail"] += 1
        elif len(hit) == 1:
            p, t, (s, e) = hit[0]
            if not dry:
                if bdir:
                    Path(bdir).mkdir(parents=True, exist_ok=True)
                    b = Path(bdir) / p.name
                    if not b.exists():
                        b.write_bytes(p.read_bytes())
                p.write_bytes((t[:s] + novo + t[e:]).encode("utf-8"))
            log(f"  OK{' (dry)' if dry else ''} {oid}: {p.name}")
            st["ok"] += 1
        elif applied:
            log(f"  VEC {oid}: vec primijenjeno u {applied[0].name}")
            st["vec"] += 1
        else:
            log(f"  WARN {oid}: sidro nije nadjeno u {fajl}")
            st["fail"] += 1
    return st


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    strict, dry = "--strict" in argv, "--dry" in argv
    if len(args) < 2:
        print("Upotreba: apply_overlay.py <checkpoint_dir> <overlay_json> [--strict] [--dry]")
        return 1
    ck, ovr = Path(args[0]), Path(args[1])
    if not ovr.exists():
        print(f"Overlay fajl {ovr} ne postoji. Preskacem.")
        return 0
    try:
        ispravke = json.loads(ovr.read_text("utf-8")).get("ispravke", [])
    except Exception as e:
        print(f"Greska pri citanju {ovr}: {e}")
        return 1
    if not ispravke:
        return 0
    print(f"Primjenjujem {len(ispravke)} ispravki iz overlay-a...")
    st = primijeni(ck, ispravke, strict, os.environ.get("OVERLAY_BACKUP_DIR"), dry)
    print(f"Rezultat: ok={st['ok']} vec={st['vec']} fail={st['fail']}")
    return 3 if (strict and st["fail"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
