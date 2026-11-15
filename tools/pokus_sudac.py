#!/usr/bin/env python3
"""L24b: ponovno sudenje prijevoda iz pokusa (tools/pokus_prijevod.py) radnim sudcem.

Prvi pokus: sudac (Groq gpt-oss-120b) je svih 18 puta vratio 'neispravan_odgovor', pa
nema mjerenja gresaka. Ovdje se NE prevodi ponovno: cita se najnoviji .logs/pokus_*/ (plain tekst
po modelu i bloku), isti EN blokovi se rekonstruiraju iz EPUB-a, a sudac se bira lancem:
  1. produkcijski sudac: GROQ + aktivni model flote, temperatura 0.05, max_tokens 2500
  2. GROQ openai/gpt-oss-120b, temperatura 0.05, max_tokens 6000
  3. GEMINI gemini-3.5-flash-lite, temperatura 0.05
Prvi koji na probnom paru vrati 'ok' ili 'greske' postaje JEDINI sudac za sve varijante.
Za neuspjele probe ispisuje se pocetak sirovog odgovora (dijagnoza).
"""
import collections
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))


def poziv(api_call, fleet, prov, model, system, user, temp, max_tokens, pokusaja=2):
    for k in range(pokusaja):
        key = fleet.get_best_key(prov)
        if not key:
            return None
        try:
            r = api_call(provider=prov, model=model, api_key=key, system=system,
                         user=user, temperature=temp, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            print(f"   ! {prov}/{model}: {type(e).__name__}: {e}")
            r = None
        if r:
            return r
        time.sleep(20.0 if k < pokusaja - 1 else 0)
    return None


def main(argv=None, api_call=None, fleet=None, sleep=time.sleep):
    import pokus_prijevod as P
    from core.chunking import chunk_html
    from core.verifier import provjeri_blok

    if api_call is None:
        from network.http_client import api_call as _ac
        api_call = _ac
    if fleet is None:
        from api_fleet import FleetManager
        fleet = FleetManager()

    dirs = sorted(glob.glob(os.path.join(".logs", "pokus_*")))
    dirs = [d for d in dirs if glob.glob(os.path.join(d, "*_blok_*.txt"))]
    if not dirs:
        raise SystemExit("nema .logs/pokus_*/ s prijevodima")
    izlaz = dirs[-1]
    epub = P.nadji_epub()
    html = P.izvuci_html(epub, "chapter001")
    chunks = [c for c in chunk_html(html, max_words=500) if len(P.plain(c).split()) >= 40][:6]

    modeli = collections.OrderedDict()
    for f in sorted(glob.glob(os.path.join(izlaz, "*_blok_*.txt"))):
        m = re.match(r"(.+)_blok_(\d+)\.txt$", os.path.basename(f))
        modeli.setdefault(m.group(1), {})[int(m.group(2))] = open(f, encoding="utf-8").read()
    print(f"izvor prijevoda: {izlaz}; varijante: {list(modeli)}; EN blokova: {len(chunks)}")

    try:
        from config.ai_config import MODEL_MAP
        groq_aktivni = fleet.get_active_model("GROQ", MODEL_MAP.get("GROQ", ""))
    except Exception:
        groq_aktivni = ""
    lanac = [
        ("GROQ", groq_aktivni, 0.05, 2500),
        ("GROQ", "openai/gpt-oss-120b", 0.05, 6000),
        ("GEMINI", "gemini-3.5-flash-lite", 0.05, 2500),
    ]
    lanac = [s for s in lanac if s[1]]

    prvi_m = next(iter(modeli))
    prvi_b = min(modeli[prvi_m])
    sudac = None
    for prov, model, temp, mt in lanac:
        def fn(prompt, sys_p, prov=prov, model=model, temp=temp, mt=mt):
            fn.zadnji = poziv(api_call, fleet, prov, model, sys_p, prompt, temp, mt)
            return fn.zadnji
        fn.zadnji = None
        v = provjeri_blok(chunks[prvi_b], modeli[prvi_m][prvi_b], {}, fleet=fn)
        st = v.get("status")
        print(f"proba suca {prov}/{model}: status={st}")
        if st in ("ok", "greske"):
            sudac = (prov, model, temp, mt)
            break
        print("   sirovi odgovor (300 zn):", repr((fn.zadnji or "")[:300]))
    if not sudac:
        raise SystemExit("nijedan sudac iz lanca ne vraca ispravan JSON: vidi sirove odgovore gore")
    prov, model, temp, mt = sudac
    print(f"SUDAC: {prov}/{model} (temp {temp}, max_tokens {mt})")

    def sudac_fn(prompt, sys_p):
        return poziv(api_call, fleet, prov, model, sys_p, prompt, temp, mt)

    rez = {}
    for m, blokovi in modeli.items():
        redovi = []
        for i in sorted(blokovi):
            if i >= len(chunks):
                continue
            v = provjeri_blok(chunks[i], blokovi[i], {}, fleet=sudac_fn)
            sleep(2.0)
            greske = v.get("greske") or []
            redovi.append({"blok": i, "status": v.get("status"), "score": v.get("score"),
                           "greske": [{"tip": g.get("tip"), "en": str(g.get("en_fragment"))[:100],
                                       "hr": str(g.get("hr_fragment"))[:100],
                                       "obj": str(g.get("objasnjenje"))[:120]} for g in greske]})
            print(f"  {m} blok {i}: {v.get('status')}, gresaka {len(greske)}")
        rez[m] = redovi

    print(f"\n=== SAZETAK SUDENJA (sudac {prov}/{model}) ===")
    print(f"{'varijanta':28}{'ocijenjeno':>11}{'valjano':>8}{'ok':>4}{'gresaka':>8}{'gr/blok':>8}")
    for m, redovi in rez.items():
        valjano = [r for r in redovi if r["status"] in ("ok", "greske")]
        gr = sum(len(r["greske"]) for r in valjano)
        okn = sum(1 for r in valjano if r["status"] == "ok")
        print(f"{m:28}{len(redovi):>11}{len(valjano):>8}{okn:>4}{gr:>8}{(gr/len(valjano) if valjano else 0):>8.2f}")
    tipovi = {m: dict(collections.Counter(g["tip"] for r in redovi for g in r["greske"])) for m, redovi in rez.items()}
    print("\nvrste gresaka:", json.dumps(tipovi, ensure_ascii=False))
    for m, redovi in rez.items():
        print(f"\n--- greske {m} ---")
        k = 0
        for r in redovi:
            for g in r["greske"]:
                if k < 8:
                    print(f"  b{r['blok']} [{g['tip']}] EN: {g['en']} | HR: {g['hr']} | {g['obj']}")
                    k += 1
    json.dump({"sudac": [prov, model], "rez": rez}, open(os.path.join(izlaz, "sudenje.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nizlaz: {izlaz}/sudenje.json")
    return rez


if __name__ == "__main__":
    main()
