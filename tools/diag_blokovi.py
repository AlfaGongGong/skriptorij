#!/usr/bin/env python3
"""Dijagnostika blokova (SAMO CITA — ne mijenja nista u projektu).

Mjeri na stvarnim chunkovima knjige:
  A  koliko ih Gemini blokira i KOJIM razlogom (isti payload kao produkcija)
  A2 je li blok ponovljiv ili slucajan (ponovi isti poziv)
  B  spasi li ga postojeci kontekst-retry (_posalji_na_gemini_s_kontekstom)
  C  prolazi li Gemma (testira pretpostavku "Gemma dijeli isti filter")
  D  bisekcija: koliko teksta prode i koliki je najmanji blokirani komad

Pokretanje (iz /root/skriptorij):
  python3 tools/diag_blokovi.py --selftest
  python3 tools/diag_blokovi.py KNJIGA.epub --uzorak 30
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter

SYS = ("Ti si profesionalni knjizevni prevodilac. Prevedi dati tekst na hrvatski "
       "jezik, vjerno i potpuno. Vrati SAMO prijevod.")
BLOCK_FINISH = {"SAFETY", "PROHIBITED_CONTENT", "RECITATION", "BLOCKLIST",
                "SPII", "IMAGE_SAFETY", "OTHER"}


class Prekid(Exception):
    """Dosegnut globalni limit poziva."""


# ── cista logika (testira se u --selftest) ───────────────────────────────────
def klasifikuj(d):
    """Vraca (status, detalj). Status: OK | BLOK | DJELIMICNO | PRAZNO | GRESKA."""
    if not d:
        return "GRESKA", "prazan odgovor"
    if "_greska" in d:
        return "GRESKA", str(d["_greska"])
    fb = d.get("promptFeedback") or {}
    if fb.get("blockReason"):
        return "BLOK", "prompt:" + fb["blockReason"]
    c = d.get("candidates") or []
    if not c:
        return "PRAZNO", "nema candidates"
    fin = c[0].get("finishReason", "")
    dijelovi = (c[0].get("content") or {}).get("parts") or []
    tekst = "".join(p.get("text", "") for p in dijelovi
                    if isinstance(p, dict) and not p.get("thought")).strip()
    if tekst:
        if fin in BLOCK_FINISH:
            return "DJELIMICNO", "odgovor:" + fin
        return "OK", fin or "STOP"
    if fin in BLOCK_FINISH:
        return "BLOK", "odgovor:" + fin
    return "PRAZNO", fin or "nepoznato"


def flagirane(d):
    """Kategorije koje su eksplicitno oznacene blocked=true."""
    out = []
    for r in ((d.get("promptFeedback") or {}).get("safetyRatings") or []):
        if r.get("blocked"):
            out.append(r.get("category", "?"))
    c = d.get("candidates") or []
    if c:
        for r in (c[0].get("safetyRatings") or []):
            if r.get("blocked"):
                out.append(r.get("category", "?"))
    return out


def podijeli(tekst):
    """Dijeli na dva dijela: po paragrafu, pa po recenici, pa po rijecima."""
    parag = [p for p in tekst.split("\n") if p.strip()]
    if len(parag) >= 2:
        k = len(parag) // 2
        return "\n".join(parag[:k]), "\n".join(parag[k:])
    rez = list(re.finditer(r"[.!?\u2026][\"\u201d\u00bb']?\s+", tekst))
    if rez:
        sredina = len(tekst) / 2
        m = min(rez, key=lambda x: abs(x.end() - sredina))
        a, b = tekst[:m.end()].strip(), tekst[m.end():].strip()
        if a and b:
            return a, b
    rijeci = tekst.split()
    if len(rijeci) < 2:
        return None
    k = len(rijeci) // 2
    return " ".join(rijeci[:k]), " ".join(rijeci[k:])


def bisekcija(tekst, proba, max_dubina=4, budzet=14):
    """proba(t) -> 'OK' | 'BLOK' | 'GRESKA'. Korijen je vec poznat kao blokiran."""
    st = {"prosle": 0, "blokirane": 0, "neprovjereno": 0,
          "najmanji": None, "primjer": None, "poziva": 0}

    def rad(t, dubina, poznat_blok):
        w = len(t.split())
        if not poznat_blok:
            if st["poziva"] >= budzet:
                st["neprovjereno"] += w
                return
            st["poziva"] += 1
            r = proba(t)
            if r == "OK":
                st["prosle"] += w
                return
            if r != "BLOK":
                st["neprovjereno"] += w
                return
        dijelovi = podijeli(t) if dubina < max_dubina else None
        if not dijelovi:
            st["blokirane"] += w
            if st["najmanji"] is None or w < st["najmanji"]:
                st["najmanji"] = w
                st["primjer"] = " ".join(t.split()[:12])
            return
        rad(dijelovi[0], dubina + 1, False)
        rad(dijelovi[1], dubina + 1, False)

    rad(tekst, 0, True)
    return st


def sazetak(rez, ctx_info):
    L = []
    n = len(rez)
    A = Counter(r["A"][0] for r in rez)
    L.append(f"Testirano chunkova: {n}  | poziva: {ctx_info['poziva']}  | 429: {ctx_info['n429']}")
    L.append("A statusi: " + ", ".join(f"{k}={v}" for k, v in A.most_common()))
    razlozi = Counter(r["A"][1] for r in rez if r["A"][0] != "OK")
    if razlozi:
        L.append("A razlozi (ne-OK): " + ", ".join(f"{k}={v}" for k, v in razlozi.most_common()))
    kat = Counter(c for r in rez for c in r.get("flag", []))
    if kat:
        L.append("Flagirane kategorije: " + ", ".join(f"{k}={v}" for k, v in kat.most_common()))
    bl = [r for r in rez if r["A"][0] in ("BLOK", "DJELIMICNO")]
    L.append(f"Blokiranih: {len(bl)} od {n}")
    if bl:
        pon = Counter(r["A2"][0] for r in bl if "A2" in r)
        L.append("A2 ponovljeno isto: " + ", ".join(f"{k}={v}" for k, v in pon.most_common()))
        B = Counter(r["B"] for r in bl if "B" in r)
        if B:
            L.append("B kontekst-retry: " + ", ".join(f"{k}={v}" for k, v in B.most_common()))
        C = Counter(r["C"][0] + ":" + r["C"][1] for r in bl if "C" in r)
        if C:
            L.append("C Gemma: " + ", ".join(f"{k}={v}" for k, v in C.most_common()))
        D = [r["D"] for r in bl if "D" in r]
        if D:
            pr = sum(d["prosle"] for d in D)
            bk = sum(d["blokirane"] for d in D)
            nv = sum(d["neprovjereno"] for d in D)
            uk = pr + bk + nv
            if uk:
                L.append(f"D bisekcija: prolazi {100 * pr / uk:.0f}% rijeci, "
                         f"blokirano {100 * bk / uk:.0f}%, neprovjereno {100 * nv / uk:.0f}%")
            naj = [d["najmanji"] for d in D if d["najmanji"] is not None]
            if naj:
                L.append(f"D najmanji blokirani komad (rijeci): min={min(naj)}, "
                         f"medijan={statistics.median(naj):.0f}, max={max(naj)}")
            L.append(f"D poziva po blokiranom chunku: prosjek "
                     f"{sum(d['poziva'] for d in D) / len(D):.1f}")
    return "\n".join(L)


# ── mrezni dio ───────────────────────────────────────────────────────────────
def gemini_poziv(model, key, payload, timeout=120):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_greska": f"HTTP {e.code}"}
    except Exception as e:  # kljuc se nikad ne ispisuje
        return {"_greska": type(e).__name__}


class Ctx:
    def __init__(self, fleet, pauza, max_poziva):
        self.fleet, self.pauza, self.max_poziva = fleet, pauza, max_poziva
        self.poziva = 0
        self.n429 = 0

    def poziv(self, prov, model, payload):
        if self.poziva >= self.max_poziva:
            raise Prekid()
        key = self.fleet.get_best_key(prov)
        if not key:
            return {"_greska": f"nema kljuca {prov}"}
        time.sleep(self.pauza)
        self.poziva += 1
        d = gemini_poziv(model, key, payload)
        if d.get("_greska") == "HTTP 429":
            self.n429 += 1
            time.sleep(30)
            d = gemini_poziv(model, key, payload)
        return d


def ucitaj_projekt():
    sys.path.insert(0, os.getcwd())
    from bs4 import BeautifulSoup
    from network.http_client import (_build_gemini_native_payload,
                                     _posalji_na_gemini_s_kontekstom)
    from core.chunking import chunk_html
    from api_fleet import get_active_fleet, FleetManager
    from config.settings import CONFIG_PATH
    fleet = get_active_fleet() or FleetManager(config_path=CONFIG_PATH)
    return (BeautifulSoup, _build_gemini_native_payload,
            _posalji_na_gemini_s_kontekstom, chunk_html, fleet)


def chunkovi_iz_epuba(putanja, chunk_html):
    out = []
    with zipfile.ZipFile(putanja) as z:
        for ime in z.namelist():
            if not ime.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            raw = z.read(ime)
            if len(raw) < 8000:  # naslovna/toc/impresum, kao u styleru
                continue
            for c in chunk_html(raw.decode("utf-8", errors="replace"), 250):
                if isinstance(c, (tuple, list)):
                    c = c[0]
                out.append((ime, c if isinstance(c, str) else str(c)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub", nargs="?")
    ap.add_argument("--uzorak", type=int, default=30, help="0 = svi chunkovi")
    ap.add_argument("--max-poziva", type=int, default=150)
    ap.add_argument("--pauza", type=float, default=4.0)
    ap.add_argument("--gemma-model", default=None)
    ap.add_argument("--bez-konteksta", action="store_true")
    ap.add_argument("--bez-gemme", action="store_true")
    ap.add_argument("--bez-bisekcije", action="store_true")
    ap.add_argument("--izvod", action="store_true",
                    help="u log upisi prvih 12 rijeci najmanjeg blokiranog komada")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.epub:
        ap.error("treba putanja do EPUB-a")

    BS, build, ctx_retry, chunk_html, fleet = ucitaj_projekt()
    gem_model = fleet.get_active_model("GEMINI")
    gemma_model = a.gemma_model or fleet.get_active_model("GEMMA")
    if not gem_model:
        print("Nema aktivnog GEMINI modela u fleetu."); return 1

    sve = chunkovi_iz_epuba(a.epub, chunk_html)
    if not sve:
        print("Nema chunkova (provjeri EPUB)."); return 1
    korak = max(1, len(sve) // a.uzorak) if a.uzorak else 1
    odabir = list(enumerate(sve))[::korak]
    if a.uzorak:
        odabir = odabir[:a.uzorak]
    print(f"Chunkova ukupno: {len(sve)}, testiram: {len(odabir)}, "
          f"gemini={gem_model}, gemma={gemma_model or 'nema'}")

    ctx = Ctx(fleet, a.pauza, a.max_poziva)
    ts = time.strftime("%H%M%S")
    izlaz = f"/tmp/diag_blokovi_{ts}.jsonl"
    rez = []

    def plain(html):
        return BS(html, "html.parser").get_text("\n")

    def proba(t):
        d = ctx.poziv("GEMINI", gem_model, build(SYS, t, 0.3, 4000))
        st, _ = klasifikuj(d)
        return "OK" if st == "OK" else ("BLOK" if st in ("BLOK", "DJELIMICNO") else "GRESKA")

    try:
        with open(izlaz, "w", encoding="utf-8") as f:
            for i, (ime, html) in odabir:
                r = {"idx": i, "fajl": ime,
                     "rijeci": len(plain(html).split())}
                d = ctx.poziv("GEMINI", gem_model, build(SYS, html, 0.3, 4000))
                r["A"] = list(klasifikuj(d))
                r["flag"] = flagirane(d) if isinstance(d, dict) else []
                if r["A"][0] in ("BLOK", "DJELIMICNO"):
                    r["A2"] = list(klasifikuj(
                        ctx.poziv("GEMINI", gem_model, build(SYS, html, 0.3, 4000))))
                    if not a.bez_konteksta:
                        try:
                            r["B"] = "OK" if ctx_retry(SYS, html, 4000, 120) else "NE"
                        except Exception as e:
                            r["B"] = "GRESKA:" + type(e).__name__
                    if gemma_model and not a.bez_gemme:
                        r["C"] = list(klasifikuj(
                            ctx.poziv("GEMMA", gemma_model, build(SYS, html, 0.3, 4000))))
                    if not a.bez_bisekcije:
                        D = bisekcija(plain(html), proba)
                        if not a.izvod:
                            D["primjer"] = None
                        r["D"] = D
                rez.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
                print(f"[{len(rez)}/{len(odabir)}] chunk {i}: {r['A'][0]} {r['A'][1]}")
    except Prekid:
        print(f"\nDosegnut limit od {a.max_poziva} poziva — prekidam i ispisujem sazetak.")
    except KeyboardInterrupt:
        print("\nPrekinuto — ispisujem sazetak onoga sto je gotovo.")

    if rez:
        txt = sazetak(rez, {"poziva": ctx.poziva, "n429": ctx.n429})
        print("\n===== SAZETAK =====\n" + txt)
        with open(f"/tmp/diag_blokovi_{ts}.txt", "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        print(f"\nDetalji: {izlaz}")
    return 0


# ── selftest (bez mreze i bez projekta) ──────────────────────────────────────
def selftest():
    assert klasifikuj(None)[0] == "GRESKA"
    assert klasifikuj({"_greska": "HTTP 429"}) == ("GRESKA", "HTTP 429")
    assert klasifikuj({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}) == \
        ("BLOK", "prompt:PROHIBITED_CONTENT")
    assert klasifikuj({"candidates": []}) == ("PRAZNO", "nema candidates")
    ok = {"candidates": [{"finishReason": "STOP",
                          "content": {"parts": [{"text": "Zdravo"}]}}]}
    assert klasifikuj(ok) == ("OK", "STOP")
    assert klasifikuj({"candidates": [{"finishReason": "SAFETY"}]}) == ("BLOK", "odgovor:SAFETY")
    rec = {"candidates": [{"finishReason": "RECITATION",
                           "content": {"parts": [{"text": "pocetak"}]}}]}
    assert klasifikuj(rec) == ("DJELIMICNO", "odgovor:RECITATION")
    assert klasifikuj({"candidates": [{"finishReason": "MAX_TOKENS"}]}) == ("PRAZNO", "MAX_TOKENS")
    mis = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "skriveno", "thought": True}]}}]}
    assert klasifikuj(mis)[0] == "PRAZNO"
    fl = {"candidates": [{"safetyRatings": [
        {"category": "HARM_CATEGORY_HARASSMENT", "blocked": True},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "blocked": False}]}]}
    assert flagirane(fl) == ["HARM_CATEGORY_HARASSMENT"]

    assert podijeli("a b\nc d\ne f") == ("a b", "c d\ne f")
    p = podijeli("Prva recenica ovdje. Druga recenica ovdje. Treca recenica ovdje.")
    assert p and p[0] and p[1] and "Druga" in p[0] + p[1]
    assert podijeli("jedna") is None
    assert podijeli("a b c d") == ("a b", "c d")

    # bisekcija: jedan 'okidac' u 24-rijecnom tekstu od 6 paragrafa
    tekst = "\n".join(["p%d r1 r2 r3" % i for i in range(5)] + ["XXX r1 r2 r3"])
    ukupno = len(tekst.split())
    st = bisekcija(tekst, lambda t: "BLOK" if "XXX" in t else "OK", max_dubina=4)
    assert st["prosle"] + st["blokirane"] + st["neprovjereno"] == ukupno, st
    # dubina 4 spusta se ispod paragrafa (na pola paragrafa = 2 rijeci)
    assert st["blokirane"] == 2 and st["najmanji"] == 2, st
    assert st["prosle"] == ukupno - 2, st
    assert st["primjer"] == "XXX r1", st

    # sve blokirano -> nista ne prolazi, najmanji je list stabla
    st2 = bisekcija(tekst, lambda t: "BLOK", max_dubina=4, budzet=100)
    assert st2["prosle"] == 0 and st2["blokirane"] == ukupno, st2
    # zadani budzet (14) se potrosi prije dna stabla -> ostatak je neprovjeren
    st2b = bisekcija(tekst, lambda t: "BLOK", max_dubina=4)
    assert st2b["poziva"] == 14 and st2b["neprovjereno"] > 0, st2b
    assert st2b["prosle"] + st2b["blokirane"] + st2b["neprovjereno"] == ukupno, st2b

    # greske se ne racunaju kao prolaz niti blok
    st3 = bisekcija(tekst, lambda t: "GRESKA", max_dubina=4)
    assert st3["prosle"] == 0 and st3["blokirane"] == 0
    assert st3["neprovjereno"] == ukupno, st3

    # budzet
    st4 = bisekcija(tekst, lambda t: "BLOK" if "XXX" in t else "OK", budzet=1)
    assert st4["poziva"] == 1
    assert st4["prosle"] + st4["blokirane"] + st4["neprovjereno"] == ukupno, st4

    rez = [{"idx": 0, "rijeci": 100, "A": ["OK", "STOP"], "flag": []},
           {"idx": 1, "rijeci": 100, "A": ["BLOK", "prompt:PROHIBITED_CONTENT"],
            "flag": [], "A2": ["BLOK", "prompt:PROHIBITED_CONTENT"], "B": "NE",
            "C": ["BLOK", "prompt:PROHIBITED_CONTENT"], "D": st}]
    s = sazetak(rez, {"poziva": 7, "n429": 0})
    assert "Blokiranih: 1 od 2" in s and "D bisekcija" in s
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
