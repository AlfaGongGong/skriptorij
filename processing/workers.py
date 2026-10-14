# processing/workers.py

import json
import re
import time
from bs4 import BeautifulSoup
from processing.parallel import AdaptiveParallelism
from core.text_utils import _HTML_TAG_RE, _detektuj_en_ostatke
from core.quality import _scoruj_kvalitetu, _QUALITY_RESCUE_THRESHOLD


# ============================================================================
# FIX #4 — Robusno JSON parsiranje AI odgovora
# ============================================================================


def _robust_json_parse(raw: str) -> dict | None:
    """
    Pokušava parsirati JSON iz AI odgovora koji može biti:
    - Čisti JSON
    - Tekst + JSON na kraju
    - Markdown JSON blok (```json...```)
    - JSON s višestrukim blokovim

    Vraća dict ili None ako parsiranje nije uspjelo.
    """
    if not raw or not raw.strip():
        return None

    # 1. Pokušaj direktno (najbrži slučaj)
    try:
        result = json.loads(raw.strip())
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Ukloni markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. Izvuci sve JSON objekte iz teksta i pokušaj svaki
    # Napredniji approach: pronađi sve { ... } blokove respektirajući ugniježđenost
    depth = 0
    start = -1
    candidates = []
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(raw[start : i + 1])
                start = -1

    # Pokušaj svaki kandidat, od najdužeg prema najkraćem
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            continue

    # 4. Pokušaj naivnu ekstrakciju od prvog { do zadnjeg }
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        chunk = raw[first_brace : last_brace + 1]
        chunk = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", chunk)
        try:
            result = json.loads(chunk)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 5. Agresivna sanacija: AI je vratio Python-style dict (jednostruki navodnici, trailing commas)
    if first_brace != -1 and last_brace > first_brace:
        chunk = raw[first_brace : last_brace + 1]

        # 5a. ast.literal_eval — razumije Python dict syntax
        try:
            import ast
            py_obj = ast.literal_eval(chunk)
            if isinstance(py_obj, dict):
                result = json.loads(json.dumps(py_obj, ensure_ascii=False))
                if isinstance(result, dict):
                    return result
        except Exception:
            pass

        # 5b. Regex sanacija: ' → ", trailing commas, liste
        try:
            fixed = chunk
            fixed = re.sub(r",\s*([\}\]])", r"\1", fixed)           # trailing commas
            fixed = re.sub(r"'([^\']*)\'(\s*:)", r'"\1"\2', fixed)  # 'key': → "key":
            fixed = re.sub(r":\s*'([^\']*)\'", r': "\1"', fixed)       # : 'val' → : "val"
            fixed = re.sub(r"'\s*,\s*'", '", "', fixed)               # 'a', 'b' → "a", "b"
            fixed = re.sub(r"\[\s*'", '["', fixed)
            fixed = re.sub(r"'\s*\]", '"]', fixed)
            result = json.loads(fixed)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    return None


# ============================================================================
# GLOSAR VALIDACIJA — FIX #4
# ============================================================================


async def _validiraj_glosar_poglavlja(engine, poglavlje_tekst: str, file_name: str):
    """
    Validacija konzistentnosti glosara na kraju poglavlja.

    Šalje kompletan prevedeni tekst poglavlja + glosar AI-u koji provjerava
    jesu li sva imena i termini konzistentno korišćeni kroz cijelo poglavlje.

    FIX #4: Koristi _robust_json_parse() umjesto naivnog regex + json.loads().
    PROBLEM 8 PATCH: Nakon detekcije problema, ažurira engine.glosar_tekst
    s ispravnim oblicima — naredna poglavlja automatski dobijaju korekcije.
    """
    from core.prompts import GLOSAR_VALIDATION_SYS

    glosar = engine.glosar_tekst
    if not glosar or not poglavlje_tekst.strip():
        return

    # Ograniči dužinu teksta da ne prekoračimo context window
    cist_tekst = BeautifulSoup(poglavlje_tekst, "html.parser").get_text()[:6000]
    prompt = (
        f"GLOSAR:\n{glosar[:1500]}\n\n"
        f"PREVEDENI TEKST POGLAVLJA:\n{cist_tekst}\n\n"
        f"Provjeri konzistentnost svih imenskih oblika iz glosara u tekstu. "
        f"Odgovori ISKLJUČIVO validnim JSON objektom — bez ikakvog teksta, objašnjenja "
        f"ili markdown-a prije ili poslije. "
        f'Primjer minimalnog validnog odgovora: {{"konzistentno": true, "problemi": [], "sa\u017eetak": "OK"}}'
    )

    try:
        raw, _ = await engine._call_ai_engine(
            prompt,
            0,
            uloga="VALIDATOR",
            filename=file_name,
            sys_override=GLOSAR_VALIDATION_SYS,
        )
        if not raw:
            return

        # FIX #4: Robusno parsiranje umjesto naivnog re.search + json.loads
        rezultat = _robust_json_parse(raw)

        # FIX #5: Ako parsiranje ne uspije, pošalji AI-u drugi poziv da pretvori odgovor u JSON
        if rezultat is None and raw and len(raw.strip()) > 10:
            engine.log(f"🔄 Glosar validacija [{file_name}]: pokušavam JSON rescue...", "tech")
            try:
                rescue_prompt = (
                    f"Sljedeći tekst sadrži analizu konzistentnosti glosara, ali nije validan JSON.\n"
                    f"Pretvori ga u tačno ovaj JSON format bez ikakvog dodatnog teksta:\n"
                    f'{{"konzistentno": true/false, "problemi": [...], "sažetak": "..."}}\n\n'
                    f"TEKST ZA KONVERZIJU:\n{raw[:1500]}"
                )
                rescue_sys = (
                    "Ti si JSON konverter. Vraćaš ISKLJUČIVO validan JSON objekat. "
                    "Prva stvar u odgovoru je { a zadnja }. Apsolutno nula teksta izvan JSON-a."
                )
                rescue_raw, _ = await engine._call_ai_engine(
                    rescue_prompt,
                    0,
                    uloga="VALIDATOR",
                    filename=file_name,
                    sys_override=rescue_sys,
                )
                if rescue_raw:
                    rezultat = _robust_json_parse(rescue_raw)
            except Exception as rescue_err:
                engine.log(f"⚠️ JSON rescue neuspješan [{file_name}]: {rescue_err}", "tech")

        if rezultat is None:
            raw_preview = raw[:200].replace("\n", " ").strip() if raw else "(prazan odgovor)"
            engine.log(
                f"⚠️ Glosar validacija [{file_name}]: odgovor nije validan JSON ni nakon rescue-a. "
                f"Raw preview: {raw_preview}",
                "tech",
            )
            return

        # Validacija strukture — osiguraj tipove
        problemi = rezultat.get("problemi", [])
        konzistentno = rezultat.get("konzistentno", True)
        sazetak = rezultat.get("sažetak", rezultat.get("sazetak", ""))

        # Osiguraj da su problemi lista diktova
        if not isinstance(problemi, list):
            problemi = []

        if not konzistentno and problemi:
            engine.log(
                f"🔍 <b>Glosar validacija [{file_name}]:</b> {sazetak}", "warning"
            )
            for p in problemi[:5]:  # Max 5 problema u logu
                if not isinstance(p, dict):
                    continue
                oblici = " / ".join(
                    p.get("oblici_nađeni", p.get("oblici_nadeni", [])) or []
                )
                preporuka = p.get("preporuka", "")
                termin = p.get("termin_original", p.get("termin", "?"))
                engine.log(
                    f"  ⚠️ <b>{termin}</b>: nađeno kao [{oblici}] → {preporuka}",
                    "warning",
                )

            # Snimaj za UI
            if "glosar_problemi" not in engine.shared_stats:
                engine.shared_stats["glosar_problemi"] = {}
            engine.shared_stats["glosar_problemi"][file_name] = {
                "problemi": problemi,
                "sazetak": sazetak,
            }

            # PROBLEM 8 PATCH: Dodaj korekcije nazad u glosar
            # kako bi naredna poglavlja koristila konzistentne prijevode.
            korekcije_dodane = 0
            for p in problemi:
                if not isinstance(p, dict):
                    continue
                termin = p.get("termin_original", p.get("termin", ""))
                preporuka = p.get("preporuka", "")
                if termin and preporuka:
                    korekcija = (
                        f"\n{termin} → {preporuka} [KOREKCIJA iz poglavlja {file_name}]"
                    )
                    if korekcija not in engine.glosar_tekst:
                        engine.glosar_tekst += korekcija
                        korekcije_dodane += 1
            if korekcije_dodane > 0:
                engine.log(
                    f"📝 Glosar ažuriran s {korekcije_dodane} korekcija iz [{file_name}]",
                    "tech",
                )
        else:
            engine.log(f"✅ Glosar validacija [{file_name}]: konzistentno.", "tech")

    except Exception as e:
        # FIX #4: Tiho logiranje — ovo NIKAD ne smije prekinuti obradu
        engine.log(
            f"⚠️ Glosar validacija [{file_name}]: preskočena ({type(e).__name__})",
            "tech",
        )


# ============================================================================
# WORKER — Obrada jednog HTML fajla (poglavlja)
# ============================================================================




def _ocisti_html_atribute(html: str) -> str:
    """
    Očisti „ i " iz HTML atributa.

    AI ponekad (uprkos pravilu u promptu) stavi tipografske navodnike u HTML atribute:
      <p class=„booklyfi-dijalog"> — POGREŠNO
      <p class="booklyfi-dijalog"> — ISPRAVNO

    Ova funkcija čisti atribute, ali NE dira tekst (sadržaj između tagova).
    """
    if not html or "<" not in html:
        return html

    import re as _re

    def _clean_tag(match):
        tag = match.group(0)
        # Ako nema „ u tagu, ništa ne mijenjaj
        if "„" not in tag and "“" not in tag and "”" not in tag:
            return tag
        # Očisti tipografske navodnike IZ TAG-a (atributi)
        tag = tag.replace("„", '"').replace("“", '"').replace("”", '"')
        # Ako ima neparan broj ", pokušaj popraviti (dodaj na kraj ako je atribut bez zatvaranja)
        # Prebroj '
        broj_single = tag.count("'")
        if broj_single % 2 == 1:
            # Dodaj ' na kraj ako ima otvoren
            tag = tag + "'"
        return tag

    try:
        return _re.sub(r'<[^>]+>', _clean_tag, html)
    except Exception:
        return html



import json as _json_pw
import re as _re_pw

_GLOGAR_PATH = "/root/skriptorij/data/kanon/knjige"
_GLOSAR_CACHE = {}


def _ucitaj_glosar(knjiga_id):
    if knjiga_id in _GLOSAR_CACHE:
        return _GLOSAR_CACHE[knjiga_id]
    from pathlib import Path as _P
    putanja = _P(_GLOGAR_PATH) / (knjiga_id + ".json")
    if not putanja.exists():
        _GLOSAR_CACHE[knjiga_id] = {}
        return {}
    try:
        data = _json_pw.loads(putanja.read_text(encoding="utf-8"))
        glosar = data.get("termini", {})
        _GLOSAR_CACHE[knjiga_id] = glosar
        return glosar
    except Exception:
        _GLOSAR_CACHE[knjiga_id] = {}
        return {}


def _glosar_u_prompt(glosar):
    if not glosar:
        return ""
    linije = ["## GLOSAR (OBAVEZNO koristi ove oblike):"]
    for en, info in sorted(glosar.items()):
        if info.get("potvrdjeno") or info.get("kategorija") in ("lik", "mjesto"):
            hr = info.get("hr", en)
            if hr and hr != en:
                linije.append("- " + en + " -> " + hr)
            else:
                linije.append("- " + en)
    return "\n".join(linije) if len(linije) > 1 else ""




# ─── AI QA SCORER ────────────────────────────────────────────────────────
_QA_SYSTEM = """Ti si sudac kvalitete knjizevnog teksta na hrvatskom.

Ocjeni tekst na skali 1-10 po kriterijima:
  - vjernost: prenosi li smisao tocno (za prijevod) / cuva li smisao
  - stil: tecan, knjizevni hrvatski
  - gramatika: bez greski (padezi, slaganje, interpunkcija)
  - konzistentnost: imena likova, termini
  - tipografija: em-crtice u dijalogu, tipografski navodnici, tri tacke

Vrati ISKLJUCIVO JSON:
{"vjernost": 9.0, "stil": 9.0, "gramatika": 10, "konzistentnost": 10, "tipografija": 10, "ukupno": 9.6, "razlog": "kratko"}
"""


def _qa_ai_ocjena(tekst, fleet):
    """
    AI QA ocjena chunka. Vraca dict {vjernost, stil, gramatika, konzistentnost, tipografija, ukupno, razlog}.
    Ako AI ne radi — vrati heuristiku.
    """
    if not fleet:
        return _qa_ocjena(tekst)

    # Ogranici tekst na 2000 znakova
    tekst_skracen = tekst[:2000]

    for provider in ["GEMINI", "GROQ", "MISTRAL", "NVIDIA", "CLOUDFLARE"]:
        try:
            key = fleet.get_best_key(provider)
            if not key:
                continue
            api_key = key.key if hasattr(key, "key") else str(key)
            model = fleet.get_active_model(provider)
            if not model:
                continue

            from network.http_client import api_call
            res = api_call(
                provider=provider, model=model, api_key=api_key,
                system=_QA_SYSTEM, user="Ocjeni:\n\n" + tekst_skracen,
                temperature=0.1, max_tokens=500, timeout=60,
            )
            if not res:
                continue

            import json as _json_qa
            import re as _re_qa
            clean = _re_qa.sub(r"```(?:json)?\s*", "", res).replace("```", "").strip()
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start < 0 or end <= start:
                continue
            data = _json_qa.loads(clean[start:end])

            # Validacija
            kriteriji = ["vjernost", "stil", "gramatika", "konzistentnost", "tipografija"]
            ocjene = {}
            for k in kriteriji:
                try:
                    ocjene[k] = float(data.get(k, 8.0))
                except (TypeError, ValueError):
                    ocjene[k] = 8.0
            ocjene["ukupno"] = round(sum(ocjene.values()) / len(kriteriji), 2)
            ocjene["razlog"] = data.get("razlog", "")
            return ocjene
        except Exception:
            continue

    # Fallback na heuristiku
    return _qa_ocjena(tekst)




# ─── Retry s QA feedbackom ───────────────────────────────────────────────
_RETRY_FEEDBACK_SYSTEM = """Ti si vrhunski knjizevni prevodilac/lektor.

Prethodni prijevod ovog teksta dobio je nizu ocjenu kvalitete.
Tvoj zadatak je DA POPRAVIS na osnovu razloga koji su navedeni.

PRAVILA:
- IJEKAVICA obavezna
- Em-crtica (—) za dijalog
- Tipografski navodnici („")
- Tri tacke kao jedan znak (…), NIKAD "..."
- Zadrzi sadrzaj, ne dodavaj ni ne brisi
- Vrati SAMO popravljeni tekst
"""


def _retry_s_feedbackom(self, tekst, original_tekst, qa, fleet, chunk_idx):
    """
    Ponovno obradi chunk s feedbackom iz QA.
    Vraca (novi_tekst, nova_qa, uspjeh).
    """
    if not fleet:
        return tekst, qa, False

    razlog = qa.get("razlog", "")
    ocjena = qa.get("ukupno", 0)

    # Pripremi feedback prompt
    feedback = (
        "PRETHODNI PRIJEVOD (ocjena " + str(ocjena) + "/10):\n"
        + tekst[:1500]
        + "\n\n"
        + "RAZLOG NISKE OCJENE:\n" + razlog
        + "\n\n"
        + "ORIGINAL (za kontekst):\n" + original_tekst[:1000]
        + "\n\n"
        + "Prevedi PONOVNO, ispravljajuci navedene probleme. Vrati SAMO tekst."
    )

    # Pozovi AI
    for provider in ["GEMINI", "GROQ", "MISTRAL", "NVIDIA", "CLOUDFLARE"]:
        try:
            key = fleet.get_best_key(provider)
            if not key:
                continue
            api_key = key.key if hasattr(key, "key") else str(key)
            model = fleet.get_active_model(provider)
            if not model:
                continue

            from network.http_client import api_call
            res = api_call(
                provider=provider, model=model, api_key=api_key,
                system=_RETRY_FEEDBACK_SYSTEM,
                user=feedback,
                temperature=0.3, max_tokens=4000, timeout=120,
            )
            if not res or len(res.strip()) < 50:
                continue

            # Normalizuj dijalog i ocisti atribute
            res, _, _ = _normalizuj_dijalog_pipeline(res)
            res = _ocisti_html_atribute(res)

            # Nova QA
            novi_qa = _qa_ai_ocjena(res, fleet)
            novi_ocjena = novi_qa.get("ukupno", 0)

            if novi_ocjena >= 9.5:
                self.log("  Retry QA uspio: " + str(ocjena) + " -> " + str(novi_ocjena), "tech")
                return res, novi_qa, True
            elif novi_ocjena > ocjena:
                self.log("  Retry QA poboljsan: " + str(ocjena) + " -> " + str(novi_ocjena), "tech")
                return res, novi_qa, False
            else:
                self.log("  Retry QA bez poboljsanja: " + str(novi_ocjena), "warning")
                continue
        except Exception as e:
            self.log("  Retry greska (" + str(provider) + "): " + str(e), "warning")
            continue

    return tekst, qa, False



def _normalizuj_dijalog_pipeline(html):
    """
    Pretvori "dijalog" u — dijalog.
    Strog regex: hvata otvarajuce navodnike na pocetku i zatvarajuce u sredini/kraju.
    Vraca (novi_html, broj_promjena, broj_navodnika_ostalo).
    """
    from bs4 import BeautifulSoup as _BS
    from bs4 import NavigableString as _NS

    soup = _BS(html, "html.parser")
    promjena = 0

    OTV = '"\u201e\u00bb\u00ab\''
    ZAT = '"\u201c\u00ab\u00bb\''

    for p in soup.find_all("p"):
        for child in list(p.children):
            if not isinstance(child, _NS):
                continue
            original = str(child)
            tekst = original

            # 1. Na pocetku: navodnik + opc. razmak -> em-crtica
            tekst = re.sub(
                r'^(\s*)[' + OTV + r']\s*',
                r'\1— ',
                tekst,
            )
            # 2. Zatvarajuci navodnik NAKON interpunkcije unutar teksta:
            #    ". "Sljedeca rijec" -> ". — Sljedeca rijec"
            tekst = re.sub(
                r'([.!?\u2026])[' + ZAT + r']\s+',
                r'\1 — ',
                tekst,
            )
            # 3. Zatvarajuci navodnik na kraju -> ukloni
            tekst = re.sub(
                r'\s*[' + ZAT + r']\s*$',
                '',
                tekst,
            )
            # 4. Zatvarajuci navodnik prije interpunkcije: 'Da!"' -> 'Da!'
            tekst = re.sub(
                r'[' + ZAT + r']([.!?\u2026])',
                r'\1',
                tekst,
            )
            # 5. Preostali navodnik prije razmaka i rijeci -> crtica
            tekst = re.sub(
                r'[' + ZAT + r']\s+(?=[A-ZČĆŠĐŽa-zčćšđž])',
                r' — ',
                tekst,
            )

            # 6. Otvarajuci navodnik NAKON interpunkcije u sredini:
            #    ". \"Sljedeca rijec\" -> ". — Sljedeca rijec"
            tekst = re.sub(
                r'([.!?\u2026])\s+[' + OTV + r']',
                r'\1 — ',
                tekst,
            )
            if tekst != original:
                child.replace_with(_NS(tekst))
                promjena += 1

    navodnika_ostalo = 0
    for p in soup.find_all("p"):
        t = p.get_text(strip=True)
        if t and t[0] in '"\u201e\u00bb\u00ab\'':
            navodnika_ostalo += 1

    return str(soup), promjena, navodnika_ostalo



def _qa_ocjena(html):
    from bs4 import BeautifulSoup as _BS
    soup = _BS(html, "html.parser")
    tekst = soup.get_text(" ", strip=True)
    rijeci = tekst.split()
    if not rijeci:
        return {"ukupno": 0, "razlog": "prazan"}
    ocjene = {}
    losi = len(_re_pw.findall(r"\b(\w+) \1\b", tekst))
    ocjene["gramatika"] = max(0, 10 - losi * 2)
    navodnici = tekst.count('"') + tekst.count('\u201e') + tekst.count('\u00bb')
    crtice = tekst.count('\u2014')
    if navodnici > 0 and crtice == 0:
        ocjene["konzistentnost"] = 5
    elif navodnici > crtice * 0.2:
        ocjene["konzistentnost"] = 7
    else:
        ocjene["konzistentnost"] = 10
    ocjene["tipografija"] = 10 if "..." not in tekst else 7
    ocjene["vjernost"] = 8
    ocjene["stil"] = 8
    ocjene["ukupno"] = round(sum(ocjene.values()) / len(ocjene), 2)
    return ocjene



async def process_single_file_worker(self, file_path):
    file_name = file_path.name
    try:
        raw_html = file_path.read_text("utf-8", errors="ignore")
    except Exception:
        return

    chunks = self.chunk_html(raw_html, max_words=500)
    if not chunks:
        return

    orig_soup = BeautifulSoup(raw_html, "html.parser")
    self.shared_stats["current_file"] = file_name
    self.shared_stats["total_file_chunks"] = len(chunks)

    if file_name not in self._chapter_order:
        self._chapter_order.append(file_name)

    # Callback za kontekst
    def get_p_ctx(chunks_list, idx):
        return self.get_context_window(chunks_list, idx, file_name)[0]

    def get_n_ctx(chunks_list, idx):
        return self.get_context_window(chunks_list, idx, file_name)[1]

    parallel = AdaptiveParallelism(self)
    results = await parallel.process_chunks_parallel(
        chunks, file_name, get_p_ctx, get_n_ctx
    )

    final_parts = []
    for i, (res, eng) in enumerate(results):
        if res is None:
            self.log(f"⚠️ Blok {i} nije obrađen, koristim original", "warning")
            final_parts.append(chunks[i])
        else:
            # VALIDACIJA 1: prekratak output (AI vratio samo dio)
            if len(res.strip()) < 50:
                self.log(
                    f"⚠️ Blok {i}: sumnjivo kratak output ({len(res)} znakova), koristim original",
                    "warning",
                )
                final_parts.append(chunks[i])
                continue

            # VALIDACIJA 2: gubitak teksta (output < 60% originala)
            orig_len = len(chunks[i].strip())
            new_len = len(res.strip())
            if orig_len > 200 and new_len < orig_len * 0.6:
                self.log(
                    f"⚠️ Blok {i}: izgubljeno {100 - int(new_len/orig_len*100)}% teksta "
                    f"({orig_len} -> {new_len})",
                    "warning",
                )
            # Ako original ima HTML tagove ali AI vratio plain text,
            # restauriraj paragrafsku strukturu da se ne izgubi formatiranje.
            if _HTML_TAG_RE.search(chunks[i]) and not _HTML_TAG_RE.search(res):
                paras = [p.strip() for p in re.split(r"\n{2,}", res) if p.strip()]
                res = "\n".join(f"<p>{p}</p>" for p in paras) if paras else f"<p>{res}</p>"
            # Očisti HTML atribute od tipografskih navodnika (Bug 1 fallback)
            res = _ocisti_html_atribute(res)
            # Normalizuj dijalog: "... -> - ...
            res, n_dijalog, n_navodnika = _normalizuj_dijalog_pipeline(res)
            if n_dijalog:
                self.log("  Dijalog normalizovan: " + str(n_dijalog) + " promjena, " + str(n_navodnika) + " navodnika ostalo", "tech")
            # QA ocjena (postojeci scorer)
            try:
                fleet = getattr(self, "fleet", None)
                engine_fn = getattr(self, "_get_prevodilac_prompt", None)
                try:
                    # _scoruj_kvalitetu je async — await direktno
                    qa_raw = await _scoruj_kvalitetu(
                        res, engine_fn, i, file_name,
                        tip_ocjenjivanja="prevod",
                    )
                    if isinstance(qa_raw, dict):
                        qa = qa_raw
                        ukupno = qa.get("ukupno", qa.get("score", 0))
                    else:
                        qa = {"ukupno": float(qa_raw)}
                        ukupno = float(qa_raw)
                except Exception as e:
                    self.log("  Scorer greska: " + str(e), "warning")
                    qa = _qa_ai_ocjena(res, fleet)
                    ukupno = qa.get("ukupno", 0)

                if ukupno < 9.5:
                    self.log("  QA: " + str(ukupno) + " < 9.5", "warning")

                    # Retry 1 — s feedbackom
                    for retry_broj in range(1, 3):  # max 2 retry-a
                        self.log("  Retry " + str(retry_broj) + "/2 s QA feedbackom...", "warning")
                        res_novi, qa_novi, uspjeh = _retry_s_feedbackom(
                            self, res, chunks[i], qa, fleet, i
                        )
                        ukupno_novi = qa_novi.get("ukupno", 0)
                        if uspjeh:
                            res = res_novi
                            qa = qa_novi
                            ukupno = ukupno_novi
                            break
                        # Prihvati ako je bolje, ali probaj još jednom
                        if ukupno_novi > ukupno:
                            res = res_novi
                            qa = qa_novi
                            ukupno = ukupno_novi
                            # Ako je i dalje < 9.5, probaj ponovno s novim feedbackom
                        else:
                            break

                    # Ako i dalje < 9.5 — ostavi u EPUB s markerom
                    if ukupno < 9.5:
                        self.log("  QA-FLAG chunk " + str(i) + " (QA=" + str(ukupno) + ")", "warning")
                        # Ubaci HTML komentar s QA podacima na početak chunka
                        try:
                            razlog_esc = str(qa.get("razlog", "")).replace("--", "")
                            marker = "<!-- QA-FLAG: ocjena=" + str(ukupno) + " razlog=" + razlog_esc[:200] + " -->\n"
                            res = marker + res
                        except Exception:
                            pass
                    else:
                        self.log("  QA: " + str(ukupno) + " OK nakon retry-a", "tech")
                else:
                    self.log("  QA: " + str(ukupno) + " OK", "tech")
            except Exception as e:
                self.log("  QA greska: " + str(e), "warning")
            # Detekcija EN ostataka
            try:
                en_ratio = _detektuj_en_ostatke(res)
                if en_ratio > 0.20:
                    self.log("  ⚠ EN ostaci: " + str(round(en_ratio*100, 1)) + "% — pokusavam rescue", "warning")
                    # Probaj rescue iz originala
                    try:
                        from processing.rescue import _spasi_od_sirovog
                        spasen = _spasi_od_sirovog(res)
                        if spasen and len(spasen) > 10:
                            res = spasen
                            self.log("  Rescue uspio", "tech")
                    except Exception:
                        pass
            except Exception:
                pass
            final_parts.append(res)

        # Ažuriraj UI povremeno
        if (i + 1) % 10 == 0:
            self.buildlive_epub()
        now = time.monotonic()
        if now - self._last_live_epub_time >= 300:
            self.buildlive_epub()
            self._last_live_epub_time = now

        self.shared_stats["current_chunk_idx"] = i + 1
        if self.global_total_chunks > 0:
            self.shared_stats["pct"] = int(
                (self.global_done_chunks / self.global_total_chunks) * 100
            )
            self.shared_stats["ok"] = (
                f"{self.global_done_chunks} / {self.global_total_chunks}"
            )

    # Chapter summary
    cijelo_poglavlje = "".join(final_parts)
    await self._generiraj_chapter_summary(file_name, cijelo_poglavlje)

    # FIX #4: Glosar validacija nikad ne smije prekinuti obradu
    try:
        await _validiraj_glosar_poglavlja(self, cijelo_poglavlje, file_name)
    except Exception as e:
        self.log(
            f"⚠️ Glosar validacija iznimka [{file_name}]: {type(e).__name__} — nastavljam",
            "tech",
        )

    body = orig_soup.body
    if body:
        body.clear()
        translated_soup = BeautifulSoup("".join(final_parts), "html.parser")
        # BUGFIX: .children vraća <html> wrapper, ne body djecu — koristimo .body
        source = translated_soup.body or translated_soup
        for child in list(source.children):
            body.append(child.extract())
        file_path.write_text(str(orig_soup), encoding="utf-8")
    else:
        file_path.write_text("".join(final_parts), encoding="utf-8")



import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# LAZY IMPORTI — ne ruše startup ako nešto nedostaje
# ─────────────────────────────────────────────────────────────
try:
    from core.model_profiles import PROFILI, get_anti_patterne, get_temp, get_max_tokens
    _profiles_ok = True
except ImportError:
    logger.warning("workers: core.model_profiles nije dostupan, koristim defaults")
    _profiles_ok = False

try:
    from core.prompts import get_system_prompt
    _prompts_v2_ok = True
except ImportError:
    logger.warning("workers: core.prompts nije dostupan, koristim fallback")
    _prompts_v2_ok = False

try:
    from core.prompt_injector import PromptInjector
    _injector_ok = True
except ImportError:
    logger.warning("workers: core.prompt_injector nije dostupan")
    _injector_ok = False

try:
    from core.kalkovi.engine import kalkovi_engine
    _kalkovi_ok = True
except ImportError:
    logger.warning("workers: kalkovi_engine nije dostupan")
    _kalkovi_ok = False

try:
    from core.validators.morfo_validator import morfo_validator
    _validator_ok = True
except ImportError:
    logger.warning("workers: morfo_validator nije dostupan")
    _validator_ok = False

try:
    from network.provider_router import provider_router_v2
    _router_v2_ok = True
except ImportError:
    logger.warning("workers: provider_router_v2 nije dostupan")
    _router_v2_ok = False

try:
    from core.quality import ocijeni_kvalitet
    _quality_ok = True
except ImportError:
    logger.warning("workers: core.quality nije dostupan")
    _quality_ok = False

try:
    from core.qa_benchmark import qa_benchmark as _qa_benchmark
    _qa_benchmark_ok = True
except ImportError:
    logger.warning("workers: core.qa_benchmark nije dostupan")
    _qa_benchmark_ok = False

# Korak 11 — Dinamicki detektor (pasivni mod)
try:
    from core.kalkovi.dinamicki_detektor import DinamickiDetektor as _DinamickiDetektor
    _detektor = _DinamickiDetektor()
    _DETEKTOR_AKTIVAN = True
except Exception:
    _DETEKTOR_AKTIVAN = False
    _detektor = None

# Korak 11b — Rod detektor (aktivni mod: korigira miješanje roda)
# NAPOMENA (popravka): koristi se DIJELJENI singleton (isti objekt kao u
# processing/pipeline.py::_get_rod_detektor), ne nova instanca — ranije
# su dvije odvojene instance gubile naucene rod-clue-ove jedna drugoj.
try:
    from core.kalkovi.rod_detektor import rod_detektor as _rod_detektor
    _ROD_DETEKTOR_AKTIVAN = True
except Exception:
    _ROD_DETEKTOR_AKTIVAN = False
    _rod_detektor = None


# ─────────────────────────────────────────────────────────────
# MODELI S VISOKIM RIZIKOM — morfo_validator se uvijek pokreće
# ─────────────────────────────────────────────────────────────
HIGH_RISK_MODELI = {
    "llama31_70b_cerebras",
    "llama33_70b_groq",
    "llama_sambanova",
    "qwen_chutes",
}

# Threshold qualiteta ispod kojeg se pokušava retry s drugim modelom
QUALITY_RETRY_THRESHOLD = 6.5
MAX_RETRIES = 3


# ─────────────────────────────────────────────────────────────
# ANTI-PATTERN ČIŠĆENJE
# ─────────────────────────────────────────────────────────────

def _ocisti_anti_patterne(tekst: str, model_ime: str) -> str:
    """
    Uklanja per-model anti-patterne iz izlaza (meta-komentari, markdown blokovi).
    Poziva se PRIJE quality scoringa.
    """
    if not _profiles_ok:
        return tekst

    patterne = get_anti_patterne(model_ime)
    ocisceno = tekst

    for pattern in patterne:
        try:
            ocisceno = re.sub(pattern, "", ocisceno, flags=re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            logger.warning(f"Anti-pattern regex greška ({pattern}): {e}")

    # Ukloni prazne linije na početku/kraju nastale čišćenjem
    ocisceno = ocisceno.strip()
    return ocisceno


# ─────────────────────────────────────────────────────────────
# WORKER KLASA
# ─────────────────────────────────────────────────────────────

class WorkerV2:
    """
    Worker za obradu jednog chunka s V10.4 pipeline-om.
    Backward compatible — može se koristiti kao zamjena za stari Worker.
    """

    def __init__(
        self,
        uloga: str = "prevodilac",
        tip_bloka: Optional[str] = None,
        book_context: Optional[Any] = None,
        chapter_summary: Optional[str] = None,
        few_shot_primjeri: Optional[List[str]] = None,
    ):
        """
        Args:
            uloga: "prevodilac" | "lektor" | "validator"
            tip_bloka: "dijalog" | "poetski" | "naracija" | "tehnicki" | None
            book_context: BookContextManager instanca (za glosar i vlastita imena)
            chapter_summary: summary tekućeg poglavlja (iz book_context.py)
            few_shot_primjeri: 3-5 primjera dobrog prijevoda iz iste knjige
        """
        self.uloga = uloga
        self.tip_bloka = tip_bloka
        self.book_context = book_context
        self.chapter_summary = chapter_summary
        self.few_shot_primjeri = few_shot_primjeri or []

    def _sklopi_prompt(self, model_ime: str, chunk_tekst: str) -> str:
        """Sklapa kompletan system prompt za ovaj chunk i model."""
        if _injector_ok:
            try:
                injector = PromptInjector()
                return injector.assemble(
                    uloga=self.uloga,
                    model=model_ime,
                    tip_bloka=self.tip_bloka,
                    glosar=getattr(self.book_context, "glosar", {}),
                    chunk_text=chunk_tekst,
                    chapter_summary=self.chapter_summary,
                    few_shot_primjeri=self.few_shot_primjeri,
                )
            except Exception as e:
                logger.warning(f"PromptInjector greška: {e} — koristim fallback prompt")

        # Fallback: prompts_v2 bez injectora
        if _prompts_v2_ok:
            try:
                return get_system_prompt(
                    uloga=self.uloga,
                    model_ime=model_ime,
                    tip_bloka=self.tip_bloka,
                )
            except Exception as e:
                logger.warning(f"prompts_v2 greška: {e} — koristim minimal prompt")

        # Minimal fallback
        return (
            "Ti si književni prevodilac. Pišeš hrvatski, ijekavica. "
            "Vraćaš samo prevedeni tekst, bez komentara."
        )

    def _api_poziv(
        self,
        provider: str,
        model_string: str,
        api_key: Optional[str],
        system_prompt: str,
        chunk_tekst: str,
        model_ime: str,
    ) -> Optional[str]:
        """
        Obavlja API poziv prema provideru.
        Vraća odgovor kao string ili None pri grešci.
        Integrira se s postojećim http_client/network slojem.
        """
        try:
            from network.http_client import api_call
        except ImportError:
            logger.error("network.http_client nije dostupan")
            return None

        temperatura = get_temp(model_ime, self.uloga) if _profiles_ok else 0.75
        max_tok = get_max_tokens(model_ime, self.uloga) if _profiles_ok else 2048

        try:
            odgovor = api_call(
                provider=provider,
                model=model_string,
                api_key=api_key,
                system=system_prompt,
                user=chunk_tekst,
                temperature=temperatura,
                max_tokens=max_tok,
            )
            return odgovor
        except Exception as e:
            logger.error(f"API poziv greška ({provider}/{model_string}): {e}")
            return None

    def _postprocessing(self, tekst: str, model_ime: str) -> str:
        """
        Post-processing pipeline:
        1. Anti-pattern čišćenje (per-model)
        2. KalkoviEngine deterministička korekcija
        3. MorfoValidator (za high-risk modele ili uvijek za validator ulogu)
        """
        # 1. Anti-pattern čišćenje
        tekst = _ocisti_anti_patterne(tekst, model_ime)

        # 2. KalkoviEngine — primijeni() vraća (tekst, n_zamjena) tuple
        if _kalkovi_ok:
            glosar = getattr(self.book_context, "glosar", {}) if self.book_context else {}
            try:
                tekst, _ = kalkovi_engine.primijeni(tekst, glosar=glosar)
            except Exception as e:
                logger.warning(f"KalkoviEngine greška: {e} — originalni tekst prolazi")

        # 3. MorfoValidator
        pokreni_validator = (
            model_ime in HIGH_RISK_MODELI
            or self.uloga == "validator"
        )
        if pokreni_validator and _validator_ok:
            try:
                tekst = morfo_validator.validiraj(tekst)
            except Exception as e:
                logger.warning(f"MorfoValidator greška: {e} — tekst prolazi bez validacije")

        # 4. Rod detektor — aktivna korekcija miješanja roda
        if _ROD_DETEKTOR_AKTIVAN and _rod_detektor is not None:
            try:
                knjiga_id = (
                    getattr(self.book_context, "knjiga_id", "")
                    or getattr(self.book_context, "naziv", "")
                    if self.book_context else ""
                )
                glosar_rod = {}
                if self.book_context:
                    raw_glosar = getattr(self.book_context, "_glosar", {})
                    glosar_rod = {
                        ime: entry.get("rod")
                        for ime, entry in raw_glosar.items()
                        if isinstance(entry, dict) and entry.get("rod") in ("M", "Ž")
                    }
                tekst, n_rod = _rod_detektor.primijeni(
                    tekst, knjiga_id=knjiga_id, glosar_rod=glosar_rod
                )
                if n_rod:
                    logger.info(f"[rod_detektor] {n_rod} rod korekcija primijenjena")
            except Exception as e:
                logger.warning(f"RodDetektor greška: {e} — tekst prolazi nepromijenjen")

        return tekst

    def obradi_chunk(
        self,
        chunk_tekst: str,
        exclude_modeli: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Glavna metoda. Obrađuje jedan chunk kroz kompletan V10.4 pipeline.

        Returns:
            {
                "tekst": str,           # obrađeni tekst
                "model_ime": str,       # korišteni model
                "provider": str,        # korišteni provider
                "quality_score": float, # quality score (0–10)
                "retries": int,         # broj ponovnih pokušaja
                "success": bool,        # da li je obrada uspjela
            }
        """
        exclude = list(exclude_modeli or [])
        retries = 0
        zadnji_tekst = chunk_tekst  # fallback = original

        while retries < MAX_RETRIES:
            # 1. Odabir modela
            if _router_v2_ok:
                routing = provider_router_v2.get_best_model(
                    uloga=self.uloga,
                    tip_bloka=self.tip_bloka,
                    exclude=exclude,
                )
            else:
                routing = None

            if not routing:
                logger.error("Nema dostupnih modela — vraćam originalni tekst")
                return {
                    "tekst": zadnji_tekst,
                    "model_ime": "none",
                    "provider": "none",
                    "quality_score": 0.0,
                    "retries": retries,
                    "success": False,
                }

            provider, model_string, api_key = routing

            # Pronađi model_ime po api_model_string-u (za profil lookup)
            model_ime = next(
                (ime for ime, p in PROFILI.items() if p.api_model_string == model_string),
                model_string,
            ) if _profiles_ok else model_string

            # 2. Sklopi prompt
            system_prompt = self._sklopi_prompt(model_ime, chunk_tekst)

            # 3. API poziv
            odgovor = self._api_poziv(
                provider=provider,
                model_string=model_string,
                api_key=api_key,
                system_prompt=system_prompt,
                chunk_tekst=chunk_tekst,
                model_ime=model_ime,
            )

            if not odgovor:
                logger.warning(f"Prazan odgovor od {model_ime} — pokušavam drugi model")
                exclude.append(model_ime)
                retries += 1
                continue

            # 4. Post-processing
            obradjeni = self._postprocessing(odgovor, model_ime)
            zadnji_tekst = obradjeni

            # 5. Quality scoring
            quality_score = 0.0
            if _quality_ok:
                try:
                    quality_score = ocijeni_kvalitet(obradjeni, chunk_tekst)
                except Exception as e:
                    logger.warning(f"Quality scoring greška: {e}")
                    quality_score = 7.0  # default

            logger.info(
                f"WorkerV2: chunk obrađen — model={model_ime} "
                f"quality={quality_score:.1f} retries={retries}"
            )

            # Korak 11a — Pasivni detektor (ne utjece na prijevod)
            if _DETEKTOR_AKTIVAN and _detektor:
                try:
                    _knjiga = (
                        getattr(self.book_context, "file_name", "")
                        or getattr(self.book_context, "naziv", "")
                        if self.book_context else ""
                    )
                    _detektor.analiziraj(
                        original=chunk_tekst,
                        prijevod=obradjeni,
                        knjiga=_knjiga,
                        chunk_idx=0,
                        quality_score=quality_score,
                    )
                except Exception:
                    pass  # Detektor nikad ne smije prekinuti pipeline

            # 6. Retry ako je quality prenizak
            if quality_score < QUALITY_RETRY_THRESHOLD and retries < MAX_RETRIES - 1:
                logger.warning(
                    f"Quality {quality_score:.1f} < {QUALITY_RETRY_THRESHOLD} — "
                    f"pokušavam bolji model (retry {retries + 1})"
                )
                exclude.append(model_ime)
                retries += 1
                continue

            return {
                "tekst": obradjeni,
                "model_ime": model_ime,
                "provider": provider,
                "quality_score": quality_score,
                "retries": retries,
                "success": True,
            }

        # Iscrpljeni retry-ji — vraćamo zadnji tekst
        logger.error(f"Iscrpljeni retry-ji ({MAX_RETRIES}) — vraćam zadnji obrađeni tekst")
        return {
            "tekst": zadnji_tekst,
            "model_ime": "fallback",
            "provider": "fallback",
            "quality_score": 0.0,
            "retries": retries,
            "success": False,
        }


    def pokreni_qa_benchmark(
        self,
        file_name: str,
        quality_scores_path: Optional[str] = None,
    ) -> None:
        """
        Korak 10: QA Benchmark — bez AI-a.
        Poziva se jednom po knjizi nakon što su svi chunkovi obrađeni.
        Sprema logs/qa_baseline_<knjiga>_<datum>.json i trend fajl.
        """
        if not _qa_benchmark_ok:
            return
        try:
            _qa_benchmark.analiziraj_fajl(
                file_name=file_name,
                quality_scores_path=quality_scores_path,
            )
        except Exception as e:
            logger.error(f"qa_benchmark greška za {file_name}: {e}")


# ─────────────────────────────────────────────────────────────
# CONVENIENCE FUNKCIJA — drop-in zamjena za stari workers.py
# ─────────────────────────────────────────────────────────────

def obradi_chunk_v2(
    chunk_tekst: str,
    uloga: str = "prevodilac",
    tip_bloka: Optional[str] = None,
    book_context: Optional[Any] = None,
    chapter_summary: Optional[str] = None,
    few_shot_primjeri: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Drop-in zamjena za stari obradi_chunk() poziv.
    Koristi kompletan V10.4 pipeline.
    """
    worker = WorkerV2(
        uloga=uloga,
        tip_bloka=tip_bloka,
        book_context=book_context,
        chapter_summary=chapter_summary,
        few_shot_primjeri=few_shot_primjeri,
    )
    return worker.obradi_chunk(chunk_tekst)


if __name__ == "__main__":
    print("WorkerV2 učitan. HIGH_RISK_MODELI:", HIGH_RISK_MODELI)
    print("KalkoviEngine dostupan:", _kalkovi_ok)
    print("MorfoValidator dostupan:", _validator_ok)
    print("RouterV2 dostupan:", _router_v2_ok)
    print("PromptsV2 dostupan:", _prompts_v2_ok)
