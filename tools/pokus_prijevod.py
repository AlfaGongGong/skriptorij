#!/usr/bin/env python3
"""P2.26 / L24: pokus kvalitete prijevoda.

Isti izvorni blokovi (Carter, prvih K blokova jednog poglavlja, chunk_html 500 rijeci
kao u produkciji), isti prompt prevodioca (core.prompts.get_prevodilac_prompt), N modela
samo za PREVODILAC prolaz. Sudac je isti za sve (core.verifier.provjeri_blok, EN naspram HR).

Nista se ne upisuje u checkpointe ni u EPUB. Izlaz: tablica na stdout i
.logs/pokus_<TS>/ (prijevodi po varijanti i JSON sazetak).

Upotreba: python3 tools/pokus_prijevod.py [--poglavlje chapter001] [--k 6]
          [--modeli gemini-3.5-flash-lite,gemini-3.5-flash,gemma-4-31b-it]
          [--sudac GROQ:openai/gpt-oss-120b]
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.getcwd())

DEFAULT_MODELI = "gemini-3.5-flash-lite,gemini-3.5-flash,gemma-4-31b-it"
DEFAULT_SUDAC = "GROQ:openai/gpt-oss-120b"
RAZMAK = {"gemini-3.5-flash": 8.0}  # 10 RPM
RAZMAK_DEFAULT = 5.0


def nadji_epub():
    kand = []
    for pat in (
        "data/*loody*hamber*.epub",
        "/root/Skriptorij/data/*loody*hamber*.epub",
        "/root/skriptorij/data/*loody*hamber*.epub",
        "/storage/emulated/0/Download/*loody*hamber*.epub",
        "/storage/emulated/0/Books/**/*loody*hamber*.epub",
    ):
        kand += glob.glob(pat, recursive=True)
    kand = [k for k in kand if "PREVEDENO" not in k and "_prevedeno" not in k.lower()]
    return kand[0] if kand else None


def izvuci_html(epub, poglavlje):
    from bs4 import BeautifulSoup

    z = zipfile.ZipFile(epub)
    imena = [n for n in z.namelist() if re.search(poglavlje + r"\.x?html?$", n)]
    if not imena:
        raise SystemExit(f"nema {poglavlje} u {epub}")
    soup = BeautifulSoup(z.read(imena[0]).decode("utf-8", "ignore"), "html.parser")
    return soup.body.decode_contents() if soup.body else str(soup)


def ucitaj_kontekst():
    for p in glob.glob(
        "/storage/emulated/0/booklyfi_checkpoints/_skr_The_bloody_chamber*/checkpoints/book_context_cache.json"
    ):
        try:
            d = json.load(open(p, encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            pass
    return {}


def plain(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def poziv(api_call, fleet, spec, system, user, max_tokens, pokusaja=3):
    """spec = 'PROVIDER:model' ili 'model' (=GEMINI). Vraca (tekst|None, sekunde)."""
    prov, _, model = spec.partition(":") if ":" in spec else ("GEMINI", "", spec)
    prov = prov.upper()
    t0 = time.time()
    for k in range(pokusaja):
        key = fleet.get_best_key(prov)
        if not key:
            return None, time.time() - t0
        try:
            r = api_call(provider=prov, model=model, api_key=key, system=system,
                         user=user, temperature=0.35, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            print(f"   ! {spec}: {type(e).__name__}: {e}")
            r = None
        if r:
            return r, time.time() - t0
        time.sleep(25.0 if k < pokusaja - 1 else 0)
    return None, time.time() - t0


def main(argv=None, api_call=None, fleet=None, sleep=time.sleep):
    ap = argparse.ArgumentParser()
    ap.add_argument("--poglavlje", default="chapter001")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--modeli", default=DEFAULT_MODELI)
    ap.add_argument("--sudac", default=DEFAULT_SUDAC)
    ap.add_argument("--epub", default="")
    a = ap.parse_args(argv)

    from core.chunking import chunk_html
    from core.prompts import get_prevodilac_prompt
    from core.verifier import provjeri_blok

    if api_call is None:
        from network.http_client import api_call as _ac
        api_call = _ac
    if fleet is None:
        from api_fleet import FleetManager
        fleet = FleetManager()

    epub = a.epub or nadji_epub()
    if not epub:
        raise SystemExit("EPUB Carter nije nadjen (data/ ili Download)")
    html = izvuci_html(epub, a.poglavlje)
    chunks = [c for c in chunk_html(html, max_words=500) if len(plain(c).split()) >= 40][: a.k]
    ctx = ucitaj_kontekst()
    modeli = [m.strip() for m in a.modeli.split(",") if m.strip()]
    ts = time.strftime("%Y%m%d_%H%M%S")
    izlaz = os.path.join(".logs", f"pokus_{ts}")
    os.makedirs(izlaz, exist_ok=True)
    print(f"EPUB: {epub}\npoglavlje {a.poglavlje}: {len(chunks)} blokova; modeli: {modeli}; sudac: {a.sudac}")

    def sudac_fn(prompt, sys_p):
        r, _ = poziv(api_call, fleet, a.sudac, sys_p, prompt, 2400)
        return r

    rez = {}
    for m in modeli:
        prev = ""
        redovi = []
        for i, ch in enumerate(chunks):
            system = get_prevodilac_prompt(ctx, "", prev[-300:], "naracija")
            hr, sek = poziv(api_call, fleet, m, system, f"Engleski tekst za prevod:\n{ch}", 4000)
            sleep(RAZMAK.get(m, RAZMAK_DEFAULT))
            en_p = plain(ch)
            if not hr:
                redovi.append({"blok": i, "ok": False, "sek": round(sek, 1)})
                print(f"  {m} blok {i}: NEUSPJEH ({sek:.0f}s)")
                continue
            hr_p = plain(hr)
            open(os.path.join(izlaz, f"{m.replace('/', '_').replace(':', '_')}_blok_{i}.txt"), "w", encoding="utf-8").write(hr_p)
            try:
                from core.kalkovi.rod_detektor import uskladi_pripovjedaca
                _, rod_n, _, rod_flag = uskladi_pripovjedaca(hr)
            except Exception:
                rod_n, rod_flag = 0, ""
            v = provjeri_blok(ch, hr, {}, fleet=sudac_fn)
            sleep(2.0)
            greske = v.get("greske") or []
            redovi.append({
                "blok": i, "ok": True, "sek": round(sek, 1),
                "omjer": round(len(hr_p.split()) / max(1, len(en_p.split())), 2),
                "status": v.get("status") or v.get("verifier"), "score": v.get("score"),
                "greske": [{"tip": g.get("tip"), "en": str(g.get("en_fragment"))[:90],
                            "hr": str(g.get("hr_fragment"))[:90]} for g in greske],
                "rod_zamjena": rod_n, "rod_nejasan": bool(rod_flag),
            })
            prev = hr_p
            print(f"  {m} blok {i}: {sek:.0f}s, gresaka {len(greske)}, status {redovi[-1]['status']}")
        rez[m] = redovi

    print("\n=== SAZETAK (greske po bloku; sudac isti za sve) ===")
    print(f"{'model':28}{'blokova':>8}{'neuspj':>7}{'gr/blok':>8}{'ok':>4}{'sek/blok':>9}{'omjer':>7}{'rod':>5}")
    sazetak = {}
    for m, redovi in rez.items():
        dobri = [r for r in redovi if r.get("ok")]
        n = len(dobri)
        gr = sum(len(r["greske"]) for r in dobri)
        okn = sum(1 for r in dobri if r.get("status") == "ok")
        sek = sum(r["sek"] for r in dobri) / n if n else 0
        om = sum(r["omjer"] for r in dobri) / n if n else 0
        rod = sum(r["rod_zamjena"] for r in dobri)
        sazetak[m] = {"blokova": len(redovi), "neuspjeh": len(redovi) - n, "greske_po_bloku": round(gr / n, 2) if n else None,
                      "ok": okn, "sek_po_bloku": round(sek, 1), "omjer": round(om, 2), "rod_zamjena": rod}
        print(f"{m:28}{len(redovi):>8}{len(redovi)-n:>7}{(gr/n if n else 0):>8.2f}{okn:>4}{sek:>9.1f}{om:>7.2f}{rod:>5}")
    tipovi = {m: dict(collections.Counter(g["tip"] for r in redovi if r.get("ok") for g in r["greske"])) for m, redovi in rez.items()}
    print("\nvrste gresaka:", json.dumps(tipovi, ensure_ascii=False))
    for m, redovi in rez.items():
        print(f"\n--- uzorak gresaka {m} ---")
        k = 0
        for r in redovi:
            for g in r.get("greske", []):
                if k < 6:
                    print(f"  [{g['tip']}] EN: {g['en']} | HR: {g['hr']}")
                    k += 1
    for m in rez:
        f = os.path.join(izlaz, f"{m.replace('/', '_').replace(':', '_')}_blok_0.txt")
        if os.path.exists(f):
            print(f"\n--- blok 0, {m} (prvih 600 znakova) ---\n{open(f, encoding='utf-8').read()[:600]}")
    json.dump({"sazetak": sazetak, "tipovi": tipovi, "redovi": rez}, open(os.path.join(izlaz, "sazetak.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nizlaz: {izlaz}")
    return sazetak


if __name__ == "__main__":
    main()
