# processing/workers.py

import asyncio
import json
import re
import time
from bs4 import BeautifulSoup
from core.text_utils import _detektuj_en_ostatke
from processing.parallel import AdaptiveParallelism


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


async def process_single_file_worker(self, file_path):
    file_name = file_path.name
    try:
        raw_html = file_path.read_text("utf-8", errors="ignore")
    except Exception:
        return

    chunks = self.chunk_html(raw_html, max_words=1500)
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
        for child in list(translated_soup.children):
            body.append(child.extract())
        file_path.write_text(str(orig_soup), encoding="utf-8")
    else:
        file_path.write_text("".join(final_parts), encoding="utf-8")