# -*- coding: utf-8 -*-
"""core/verifier.py — P2.1 (T3) AI verifikator smisla EN vs HR.

Model dobija EN izvornik i HR prijevod jednog bloka i trazi SAMO greske smisla
(izostavljeno, dodano, kriv smisao, negacija, broj, ime iz glosara). Ne
prevodi i ne lektorira. Dopunjuje determinsticki core.metrics.check_accuracy.

Ulaz:  provjeri_blok(en_text, hr_text, glosar, fleet=None, timeout=60.0)
       provjeri_blok_async(...)  — isti ugovor, za pozive iz async koda.

`fleet` je callable `fleet(prompt: str, sys_prompt: str)` (sync ili async) koji
vraca `str` ili `(str, provider)`. Pipeline-hook (DeepSeek) pravi tanak adapter
oko self._call_ai_engine; ovaj modul NE importa pipeline ni provider-e.

Izlaz (uvijek isti oblik, nikad exception):
    {
      "ok": bool,          # True SAMO ako je provjera uspjela i nema gresaka
      "status": str,       # ok | greske | prazan_ulaz | predug_blok | nema_modela
                           # | timeout | greska_modela | neispravan_odgovor
      "provjeren": bool,   # False => model nije dao upotrebljiv odgovor;
                           #   ok je tada False, ali to NIJE nalaz o prijevodu
      "greske": [{"tip","en_fragment","hr_fragment","objasnjenje"}],
      "score": float|None, # 1.0-10.0 (kao quality.py); None ako nije provjeren
      "model": str,        # provider koji je odgovorio ("" ako nepoznat)
      "odbaceno": int,     # broj prijava koje nisu prosle provjeru integriteta
      "error": str,        # kratak razlog kad provjeren=False
    }

Integritet (P11): fragment koji model navede mora se doslovno (nakon
normalizacije razmaka/navodnika/crtica) nalaziti u EN odnosno HR tekstu.
Nepostojeci fragment se brise; prijava bez ijednog potvrdjenog fragmenta se
odbacuje (halucinacija). Ako su sve prijave odbacene, status je "ok" a
`odbaceno` > 0 — potrosac to moze logirati.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import html as _html
import inspect
import json
import logging
import re

logger = logging.getLogger(__name__)

TIPOVI = ("izostavljeno", "dodano", "kriv_smisao", "negacija", "broj", "ime", "ostalo")
# Kazne za score (skala 1-10, isto kao core/quality.py)
_KAZNE = {
    "negacija": 3.0,
    "kriv_smisao": 2.5,
    "izostavljeno": 2.0,
    "broj": 2.0,
    "dodano": 1.5,
    "ime": 1.5,
    "ostalo": 1.0,
}
MAX_ZNAKOVA = 12000      # po jeziku; veci blok => "predug_blok" (ne rezemo — laznom OK-u)
MAX_GRESAKA = 10
MAX_FRAGMENT = 300
MAX_OBJASNJENJE = 400
MAX_GLOSAR = 30
DEFAULT_TIMEOUT = 60.0

_NEUSPJEH_PROVIDERI = {"CONTENT_FILTER", "FAILED", "ERROR", "NONE"}

SYS_PROMPT = (
    "Ti si strogi provjeravatelj tocnosti prijevoda s engleskog na hrvatski. "
    "NE prevodis i NE lektoriras. Usporedjujes ENGLESKI IZVORNIK i HRVATSKI "
    "PRIJEVOD jednog bloka i trazis ISKLJUCIVO greske smisla:\n"
    "- izostavljeno: nesto iz izvornika nedostaje u prijevodu\n"
    "- dodano: prijevod sadrzi nesto cega nema u izvorniku\n"
    "- kriv_smisao: smisao je promijenjen ili pogresno shvacen\n"
    "- negacija: negacija izgubljena, dodana ili obrnuta\n"
    "- broj: broj, kolicina ili datum razlicit\n"
    "- ime: ime iz GLOSARA preveden drugacije od glosara\n"
    "- ostalo: druga ozbiljna greska smisla\n\n"
    "NE prijavljuj: stilske razlike, slobodniji ali vjeran prijevod, redoslijed "
    "rijeci, sinonime, interpunkciju, tipografiju, razlike u duljini rijecnika.\n"
    "NE prijavljuj ni rod (muski/zenski) osoba i stvari: engleski ga ne odredjuje, "
    "pa ga ne mozes provjeriti.\n"
    "Fragmenti moraju biti DOSLOVNO kopirani iz teksta (kratki, do ~15 rijeci). "
    "Kod 'izostavljeno' je hr_fragment prazan, kod 'dodano' je en_fragment prazan. "
    "Najvise 8 gresaka, najvaznije prve.\n\n"
    "Odgovori ISKLJUCIVO jednim JSON objektom, bez markdowna, bez <out> oznaka "
    "i bez teksta izvan JSON-a:\n"
    '{"ok": true|false, "greske": [{"tip": "...", "en_fragment": "...", '
    '"hr_fragment": "...", "objasnjenje": "..."}]}\n'
    'Ako nema gresaka: {"ok": true, "greske": []}'
)


# ── pomocne: tekst ──────────────────────────────────────────────────────────
def _plain(t) -> str:
    """HTML -> plain; blok-tagovi postaju prelom reda (kao metrics._plain_za_provjeru)."""
    t = re.sub(r"</?(?:p|div|br|li|h[1-6]|section|blockquote)\b[^>]*>", "\n",
               t if isinstance(t, str) else "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return _html.unescape(t).strip()


_NORM_TAB = str.maketrans({
    "„": '"', "“": '"', "”": '"', "«": '"', "»": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "–": "-", "—": "-", "‒": "-", "―": "-", "…": "...", "\u00a0": " ",
})


def _norm(t) -> str:
    t = (t if isinstance(t, str) else "").translate(_NORM_TAB)
    return re.sub(r"\s+", " ", t).strip().casefold()


def _izaberi_glosar(en_plain: str, glosar) -> dict:
    """Samo imena koja se pojavljuju u EN bloku (kao metrics.imena_nedostaju)."""
    if not isinstance(glosar, dict) or not glosar:
        return {}
    out = {}
    for en_ime, hr_ime in glosar.items():
        if not isinstance(en_ime, str) or not en_ime.strip():
            continue
        if re.search(r"\b" + re.escape(en_ime) + r"\b", en_plain):
            out[en_ime] = str(hr_ime)
            if len(out) >= MAX_GLOSAR:
                break
    return out


def napravi_prompt(en_plain: str, hr_plain: str, glosar_sel: dict) -> tuple:
    """Vraca (prompt, sys_prompt)."""
    dijelovi = []
    if glosar_sel:
        dijelovi.append("GLOSAR (EN -> HR):\n" + "\n".join(
            "%s -> %s" % (k, v) for k, v in glosar_sel.items()))
    dijelovi.append("ENGLESKI IZVORNIK:\n<<<\n%s\n>>>" % en_plain)
    dijelovi.append("HRVATSKI PRIJEVOD:\n<<<\n%s\n>>>" % hr_plain)
    dijelovi.append("Vrati JSON.")
    return "\n\n".join(dijelovi), SYS_PROMPT


# ── pomocne: parsiranje odgovora ────────────────────────────────────────────
_OMOTAC_RE = re.compile(r"</?(?:out|output|result|translation|json)\s*>", re.I)
_FENCE_RE = re.compile(r"```(?:json|JSON)?")


def izvuci_json(raw) -> dict | None:
    """Prvi ispravan JSON objekt iz odgovora modela (ogradjen ili okruzen tekstom)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    t = _FENCE_RE.sub("", _OMOTAC_RE.sub("", raw)).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    start = t.find("{")
    while start != -1:
        dubina, u_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if u_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    u_str = False
                continue
            if c == '"':
                u_str = True
            elif c == "{":
                dubina += 1
            elif c == "}":
                dubina -= 1
                if dubina == 0:
                    try:
                        obj = json.loads(t[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except (ValueError, TypeError):
                        pass
                    break
        start = t.find("{", start + 1)
    return None


def _skrati(v, n: int) -> str:
    return (v if isinstance(v, str) else ("" if v is None else str(v))).strip()[:n]


def normaliziraj_greske(sirove, en_plain: str, hr_plain: str) -> tuple:
    """-> (greske, odbaceno). Provjera integriteta fragmenata (P11)."""
    if not isinstance(sirove, list):
        return [], 0
    en_n, hr_n = _norm(en_plain), _norm(hr_plain)
    out, vidjeno, odbaceno = [], set(), 0
    for g in sirove:
        if not isinstance(g, dict):
            odbaceno += 1
            continue
        tip = _skrati(g.get("tip"), 40).lower()
        if tip not in TIPOVI:
            tip = "ostalo"
        en_f = _skrati(g.get("en_fragment"), MAX_FRAGMENT)
        hr_f = _skrati(g.get("hr_fragment"), MAX_FRAGMENT)
        if en_f and _norm(en_f) not in en_n:
            en_f = ""
        if hr_f and _norm(hr_f) not in hr_n:
            hr_f = ""
        if not en_f and not hr_f:     # nista potvrdjeno => halucinacija / neprovjerljivo
            odbaceno += 1
            continue
        kljuc = (tip, _norm(en_f), _norm(hr_f))
        if kljuc in vidjeno:
            continue
        vidjeno.add(kljuc)
        if len(out) < MAX_GRESAKA:
            out.append({
                "tip": tip,
                "en_fragment": en_f,
                "hr_fragment": hr_f,
                "objasnjenje": _skrati(g.get("objasnjenje"), MAX_OBJASNJENJE),
            })
    return out, odbaceno


def izracunaj_score(greske: list) -> float:
    return round(max(1.0, 10.0 - sum(_KAZNE.get(g["tip"], 1.0) for g in greske)), 1)


def _rezultat(status, *, ok=False, greske=None, score=None, model="",
              odbaceno=0, error="") -> dict:
    return {
        "ok": bool(ok),
        "status": status,
        "provjeren": status in ("ok", "greske"),
        "greske": greske or [],
        "score": score,
        "model": model or "",
        "odbaceno": odbaceno,
        "error": error,
    }


def _raspakiraj(res) -> tuple:
    """Odgovor fleet-a -> (raw_str, provider_str)."""
    if isinstance(res, (tuple, list)):
        raw = res[0] if res else ""
        prov = res[1] if len(res) > 1 else ""
        return (raw if isinstance(raw, str) else ""), str(prov or "")
    return (res if isinstance(res, str) else ""), ""


def obradi_odgovor(res, en_plain: str, hr_plain: str) -> dict:
    """Sirovi odgovor fleet-a -> rezultat verifikatora (cista funkcija, bez I/O)."""
    raw, prov = _raspakiraj(res)
    if prov.upper() in _NEUSPJEH_PROVIDERI:
        return _rezultat("greska_modela", model=prov, error="provider: %s" % prov)
    if not raw.strip():
        return _rezultat("neispravan_odgovor", model=prov, error="prazan odgovor modela")
    obj = izvuci_json(raw)
    if obj is None or ("ok" not in obj and "greske" not in obj):
        return _rezultat("neispravan_odgovor", model=prov,
                         error="odgovor nije ispravan JSON {ok, greske}")
    sirove = obj.get("greske", [])
    if sirove is None:
        sirove = []
    if not isinstance(sirove, list):
        return _rezultat("neispravan_odgovor", model=prov, error="'greske' nije lista")
    greske, odbaceno = normaliziraj_greske(sirove, en_plain, hr_plain)
    if not greske and not sirove and obj.get("ok") is False:
        # model javlja problem ali ne navodi sta — ne smijemo to prikazati kao OK
        greske = [{"tip": "ostalo", "en_fragment": "", "hr_fragment": "",
                   "objasnjenje": "Model javlja problem bez detalja."}]
    if greske:
        return _rezultat("greske", ok=False, greske=greske,
                         score=izracunaj_score(greske), model=prov, odbaceno=odbaceno)
    return _rezultat("ok", ok=True, score=10.0, model=prov, odbaceno=odbaceno)


def _pripremi(en_text, hr_text, glosar, fleet) -> tuple:
    """-> (gotov_rezultat|None, prompt, sys_prompt, en_plain, hr_plain)."""
    en_p, hr_p = _plain(en_text), _plain(hr_text)
    if not en_p or not hr_p:
        return _rezultat("prazan_ulaz", error="EN ili HR blok je prazan"), "", "", en_p, hr_p
    if len(en_p) > MAX_ZNAKOVA or len(hr_p) > MAX_ZNAKOVA:
        return _rezultat("predug_blok", error="blok > %d znakova" % MAX_ZNAKOVA), "", "", en_p, hr_p
    if fleet is None or not callable(fleet):
        return _rezultat("nema_modela", error="fleet nije zadan"), "", "", en_p, hr_p
    prompt, sys_p = napravi_prompt(en_p, hr_p, _izaberi_glosar(en_p, glosar))
    return None, prompt, sys_p, en_p, hr_p


_TIMEOUT_GRESKE = (asyncio.TimeoutError, TimeoutError, concurrent.futures.TimeoutError)


# ── async API ───────────────────────────────────────────────────────────────
async def provjeri_blok_async(en_text, hr_text, glosar, fleet=None,
                              timeout: float = DEFAULT_TIMEOUT) -> dict:
    gotov, prompt, sys_p, en_p, hr_p = _pripremi(en_text, hr_text, glosar, fleet)
    if gotov is not None:
        return gotov

    async def _run():
        if inspect.iscoroutinefunction(fleet):
            return await fleet(prompt, sys_p)
        loop = asyncio.get_running_loop()
        r = await loop.run_in_executor(None, fleet, prompt, sys_p)
        if inspect.isawaitable(r):      # lambda koji vraca coroutine (adapter)
            r = await r
        return r

    try:
        res = await asyncio.wait_for(_run(), timeout)
    except _TIMEOUT_GRESKE:
        return _rezultat("timeout", error="model nije odgovorio za %.1fs" % timeout)
    except Exception as e:  # noqa: BLE001 — verifikator nikad ne smije srusiti pipeline
        logger.warning("[verifier] fleet greska: %s", e)
        return _rezultat("greska_modela", error="%s: %s" % (type(e).__name__, e))
    return obradi_odgovor(res, en_p, hr_p)


# ── sync API ────────────────────────────────────────────────────────────────
def provjeri_blok(en_text, hr_text, glosar, fleet=None,
                  timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Sync varijanta. Radi i unutar pokrenutog event loop-a (poziv ide u worker thread).

    Napomena: kod timeout-a worker thread se ne moze prekinuti — ostaje da
    dovrsi u pozadini, a rezultat se ignorira.
    """
    gotov, prompt, sys_p, en_p, hr_p = _pripremi(en_text, hr_text, glosar, fleet)
    if gotov is not None:
        return gotov

    def _worker():
        r = fleet(prompt, sys_p)
        if inspect.isawaitable(r):
            async def _await(a):
                return await a
            r = asyncio.run(_await(r))
        return r

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        res = ex.submit(_worker).result(timeout=timeout)
    except _TIMEOUT_GRESKE:
        return _rezultat("timeout", error="model nije odgovorio za %.1fs" % timeout)
    except Exception as e:  # noqa: BLE001
        logger.warning("[verifier] fleet greska: %s", e)
        return _rezultat("greska_modela", error="%s: %s" % (type(e).__name__, e))
    finally:
        ex.shutdown(wait=False)
    return obradi_odgovor(res, en_p, hr_p)
