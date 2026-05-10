"""
BooklyFi — processing/workers_v2.py
V10.4: Worker koji koristi ProviderRouterV2 + PromptsV2 + PromptInjector.
Nasljednik processing/workers.py — backward compatible.

Tijek jednog chunka:
  1. ProviderRouterV2 bira optimalni model
  2. PromptInjector sklapa system prompt (base + model patch + tip bloka +
     glosar + chapter summary + few-shot + morfologija blacklist)
  3. API poziv s optimalnom temperaturom iz ModelProfile
  4. Per-model anti-pattern čišćenje PRIJE quality scoringa
  5. KalkoviEngine deterministička korekcija
  6. MorfoValidator AI prolaz (samo za modele s visokim rizikom)
  7. Quality scoring
  8. Atomični upis .chk fajla
"""

import logging
import re
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# LAZY IMPORTI — ne ruše startup ako nešto nedostaje
# ─────────────────────────────────────────────────────────────
try:
    from core.model_profiles import PROFILI, get_anti_patterne, get_temp, get_max_tokens
    _profiles_ok = True
except ImportError:
    logger.warning("workers_v2: core.model_profiles nije dostupan, koristim defaults")
    _profiles_ok = False

try:
    from core.prompts_v2 import get_system_prompt, get_temperatura, get_max_tokens as gmt_v2
    _prompts_v2_ok = True
except ImportError:
    logger.warning("workers_v2: core.prompts_v2 nije dostupan, koristim core.prompts")
    _prompts_v2_ok = False

try:
    from core.prompt_injector import PromptInjector
    _injector_ok = True
except ImportError:
    logger.warning("workers_v2: core.prompt_injector nije dostupan")
    _injector_ok = False

try:
    from core.kalkovi.engine import kalkovi_engine
    _kalkovi_ok = True
except ImportError:
    logger.warning("workers_v2: kalkovi_engine nije dostupan")
    _kalkovi_ok = False

try:
    from core.validators.morfo_validator import morfo_validator
    _validator_ok = True
except ImportError:
    logger.warning("workers_v2: morfo_validator nije dostupan")
    _validator_ok = False

try:
    from network.provider_router_v2 import provider_router_v2
    _router_v2_ok = True
except ImportError:
    logger.warning("workers_v2: provider_router_v2 nije dostupan")
    _router_v2_ok = False

try:
    from core.quality import ocijeni_kvalitet
    _quality_ok = True
except ImportError:
    logger.warning("workers_v2: core.quality nije dostupan")
    _quality_ok = False

try:
    from core.qa_benchmark import qa_benchmark as _qa_benchmark
    _qa_benchmark_ok = True
except ImportError:
    logger.warning("workers_v2: core.qa_benchmark nije dostupan")
    _qa_benchmark_ok = False

# Korak 11 — Dinamicki detektor (pasivni mod)
try:
    from core.kalkovi.dinamicki_detektor import DinamickiDetektor as _DinamickiDetektor
    _detektor = _DinamickiDetektor()
    _DETEKTOR_AKTIVAN = True
except Exception as _det_e:
    _DETEKTOR_AKTIVAN = False
    _detektor = None

# Korak 11b — Rod detektor (aktivni mod: korigira miješanje roda)
try:
    from core.kalkovi.rod_detektor import RodDetektor as _RodDetektor
    _rod_detektor = _RodDetektor()
    _ROD_DETEKTOR_AKTIVAN = True
except Exception as _rod_e:
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
