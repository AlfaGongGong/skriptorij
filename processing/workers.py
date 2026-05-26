# processing/workers.py

import json
import re
import time
from bs4 import BeautifulSoup
from processing.parallel import AdaptiveParallelism
from core.text_utils import _HTML_TAG_RE


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

    chunks = self.chunk_html(raw_html, max_words=800)
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
            # Ako original ima HTML tagove ali AI vratio plain text,
            # restauriraj paragrafsku strukturu da se ne izgubi formatiranje.
            if _HTML_TAG_RE.search(chunks[i]) and not _HTML_TAG_RE.search(res):
                paras = [p.strip() for p in re.split(r"\n{2,}", res) if p.strip()]
                res = "\n".join(f"<p>{p}</p>" for p in paras) if paras else f"<p>{res}</p>"
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
try:
    from core.kalkovi.rod_detektor import RodDetektor as _RodDetektor
    _rod_detektor = _RodDetektor()
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
            "Ti si književni prevodilac. Pišeš bosanski/hrvatski, ijekavica. "
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
                        ime: entry.get("rod", "auto")
                        for ime, entry in raw_glosar.items()
                        if isinstance(entry, dict)
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
