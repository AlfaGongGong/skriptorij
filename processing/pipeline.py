"""
processing/pipeline.py — v3.1 (Bugfix uvezivanja workers_v2)

IZMJENE vs v3.0:
  - Ispravljen potpis obradi_chunk_v2 — prima self + argumente (ne samo chunk)
  - Dodan _norm_score fallback za slučaj da quality nije float
  - _init_book_context: morfo_validator se inicijalizira iz fleet-a, ne iz gemini_api_key
  - process_chunk_with_retry: ispravan async poziv _obradi_chunk_v2
  - Dodat USE_WORKERS_V2 env fallback na "1" (aktivan po defaultu)
  - Korak 7: Nezavisni scorer — bilježenje prevoditelja za quality_scorer_v2
"""

import gc
import asyncio
import re
import json
import os as _os
from bs4 import BeautifulSoup
from core.text_utils import (
    _smart_extract,
    _agresivno_cisti,
    _detektuj_en_ostatke,
    _detektuj_halucinaciju,
    _post_process_tipografija,
    _automatska_korekcija,
    detektuj_tip_bloka,
)
from processing.rescue import _spasi_od_sirovog

# ── Korak 2, 3, 4 integracije ──────────────────────────────────────────────
try:
    from core.kalkovi.engine import kalkovi_engine
    _KALKOVI_OK = True
except ImportError:
    kalkovi_engine = None
    _KALKOVI_OK = False

try:
    from core.validators.morfo_validator import MorfoValidator
    _MORFO_OK = True
except ImportError:
    MorfoValidator = None
    _MORFO_OK = False

try:
    from analysis.book_context import BookContext
    _BOOK_CTX_OK = True
except ImportError:
    BookContext = None
    _BOOK_CTX_OK = False

try:
    from core.prompt_injector import PromptInjector
    _INJECTOR_OK = True
except ImportError:
    PromptInjector = None
    _INJECTOR_OK = False

# ── V10.4 workers_v2 integracija ────────────────────────────────────────────
USE_WORKERS_V2: bool = _os.environ.get("BOOKLYFI_V2", "1").strip() == "1"

try:
    from processing.workers_v2 import WorkerV2
    _V2_DOSTUPAN = True
except ImportError:
    WorkerV2 = None
    _V2_DOSTUPAN = False
    USE_WORKERS_V2 = False

# Korak 7 — Nezavisni scorer (odvojeni try, nema veze s WorkerV2)
try:
    from core.quality_scorer_v2 import zabilježi_prevoditelja as _zabilježi_prev
    _SCORER_V2_OK = True
except ImportError:
    _zabilježi_prev = None
    _SCORER_V2_OK = False


# ── Privatni checkpoint helperi ───────────────────────────────────────────────

def _chk_path(self, file_name: str, chunk_idx: int, suffix: str = "") -> object:
    if suffix:
        return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.{suffix}.chk"
    return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"


def _chk_read(self, file_name: str, chunk_idx: int, suffix: str = "") -> str | None:
    from utils.checkpoint_cleaner import _je_placeholder, _ocisti_json_wrapper
    p = _chk_path(self, file_name, chunk_idx, suffix)
    if not p.exists():
        return None
    try:
        tekst = p.read_text("utf-8", errors="ignore")
        tekst = _ocisti_json_wrapper(tekst)
        if len(tekst) > 10 and not _je_placeholder(tekst):
            return tekst
    except Exception:
        pass
    return None


def _chk_write(self, file_name: str, chunk_idx: int, sadrzaj: str, suffix: str = "") -> None:
    p = _chk_path(self, file_name, chunk_idx, suffix)
    self._atomic_write(p, sadrzaj)


def _strip_ai_json(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"```\s*$", "", t)
    return t.strip()


def _je_placeholder_lokalni(tekst: str) -> bool:
    if not tekst or not tekst.strip():
        return True
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    if len(cist) < 15:
        return True
    _exact = {
        "lektorisani tekst ovdje",
        "korigirani tekst ovdje",
        "molim te, pošalji tekst za obradu. čekam ga.",
        "pošalji tekst za obradu.",
        "čekam ga.",
        "[prijevod]", "[translation]", "[tekst]", "[text]",
        "placeholder", "[prijevod ovdje]", "[lektura ovdje]",
    }
    if cist in _exact:
        return True
    _contains = [
        "molim te, pošalji tekst",
        "čekam ga",
        "pošalji tekst za obradu",
        "naravno, evo lektoriranog",
        "naravno, evo prijevoda",
        "evo lektoriranog teksta:",
        "evo prijevoda:",
        "evo korigiranog teksta:",
        "svakako, evo",
        "kao što ste tražili",
        "kao što si tražio",
    ]
    if len(cist) < 150:
        for fraza in _contains:
            if fraza in cist:
                return True
    return False


def _norm_score(v) -> float:
    if isinstance(v, dict):
        return float(v.get("score", 0.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── Korak 5: Helper za kalkove + validator ──────────────────────────────────

def _primijeni_kalkove_i_validator(self, finalno: str, file_name: str, chunk_idx: int) -> str:
    """
    Primjenjuje kalkovi engine (Korak 2) i morfo validator (Korak 3).
    Fail-safe: ako bilo što ne uspije, vraća originalni tekst.
    """
    import logging

    # Korak 2: Kalkovi engine
    if _KALKOVI_OK and kalkovi_engine is not None:
        try:
            glosar = {}
            if hasattr(self, "book_context") and self.book_context:
                glosar = getattr(self.book_context, "glosar", {})
            finalno_k = kalkovi_engine.primijeni(finalno, glosar=glosar)
            if finalno_k and len(finalno_k.strip()) > 10:
                finalno = finalno_k
        except Exception as e:
            logging.warning(f"[pipeline] Kalkovi engine greška (blok {chunk_idx}): {e}")

    # Korak 3: Morfo validator
    validator = getattr(self, "morfo_validator", None)
    if validator and len(finalno.strip()) > 50:
        try:
            finalno = validator.validiraj(finalno, knjiga_id=file_name, chunk_id=chunk_idx)
        except Exception as e:
            logging.warning(f"[pipeline] Morfo validator greška (blok {chunk_idx}): {e}")

    return finalno


def _init_book_context(self, knjiga_id: str):
    """
    Inicijalizira BookContext i PromptInjector za datu knjigu (Korak 4).
    Pozvati jednom na početku obrade knjige.
    """
    import logging

    if getattr(self, "book_context", None) is not None:
        return  # već inicijalizirano

    if _BOOK_CTX_OK and BookContext is not None:
        self.book_context = BookContext(knjiga_id=knjiga_id)
    else:
        self.book_context = None

    if _INJECTOR_OK and PromptInjector is not None and self.book_context:
        self.prompt_injector = PromptInjector(book_context=self.book_context)
    else:
        self.prompt_injector = None

    # MorfoValidator — uzima ključ iz fleet managera ako je dostupan
    if _MORFO_OK and MorfoValidator is not None:
        try:
            fleet = getattr(self, "fleet", None)
            api_key = None
            if fleet:
                key_state = fleet.get_best_key("GEMINI", "VALIDATOR")
                if key_state:
                    api_key = key_state.key if hasattr(key_state, "key") else None
            # Fallback na direktni atribut
            if not api_key:
                api_key = getattr(self, "gemini_api_key", None)

            self.morfo_validator = MorfoValidator(
                api_key=api_key,
                skip_ai=(api_key is None),
            )
        except Exception as e:
            logging.warning(f"[pipeline] MorfoValidator init greška: {e}")
            self.morfo_validator = None
    else:
        self.morfo_validator = None

    logging.info(
        f"[pipeline] BookContext={'OK' if self.book_context else 'N/A'} | "
        f"MorfoValidator={'OK' if getattr(self, 'morfo_validator', None) else 'N/A'} | "
        f"knjiga={knjiga_id}"
    )


# ── Quality scoring helper ────────────────────────────────────────────────────

async def _quality_scoring(
    self, finalno: str, original_chunk, chunk_idx: int,
    file_name: str, tip_bloka: str, prov_label: str,
    tip_ocjenjivanja: str = "opci",
    prevodilac_provider: str = None,
) -> None:
    _PARATEKST_KW = (
        "halftitle", "title", "otherbyauthor", "alsoby", "seriespage",
        "copyright", "dedication", "contents", "toc", "colophon",
        "frontmatter", "backmatter", "epigraph", "acknowledgment",
        "aboutauthor", "cover", "insert",
    )
    fn_lower = file_name.lower().replace("_", "").replace("-", "")
    je_paratekst = any(kw in fn_lower for kw in _PARATEKST_KW)

    stem_key = f"{file_name}_blok_{chunk_idx}"
    if not hasattr(self, "_quality_scores"):
        self._quality_scores = {}
    if "quality_scores" not in self.shared_stats:
        self.shared_stats["quality_scores"] = {}

    if je_paratekst:
        score_float = 8.5
        self._quality_scores[stem_key] = score_float
        self.shared_stats["quality_scores"][stem_key] = score_float
        self.log(f"[{file_name}] Blok {chunk_idx}: paratekst → ocjena {score_float}", "tech")
        return

    try:
        from core.quality import _scoruj_kvalitetu
        score = await _scoruj_kvalitetu(
            finalno,
            self._call_ai_engine,
            chunk_idx,
            file_name,
            self_obj=self,
            tip_ocjenjivanja=tip_ocjenjivanja,
            prevodilac_provider=prevodilac_provider,
        )
        score_float = float(max(1.0, min(10.0, score)))

        preview = BeautifulSoup(finalno, "html.parser").get_text()[:80]
        self._quality_scores[stem_key] = score_float
        self.shared_stats["quality_scores"][stem_key] = score_float

        if score_float < 6.5:
            self.log(
                f"⚠️ Blok {chunk_idx} [{tip_bloka}]: score={score_float:.1f} — {preview[:60]}…",
                "warning",
            )
            hr_path = self.checkpoint_dir / "human_review.json"
            try:
                hr_data = json.loads(_strip_ai_json(hr_path.read_text("utf-8"))) \
                          if hr_path.exists() else []
                if not any(item.get("stem") == stem_key for item in hr_data):
                    hr_data.append({
                        "stem": stem_key,
                        "score": score_float,
                        "tip": tip_bloka,
                        "preview": preview,
                    })
                    self._atomic_write(
                        hr_path,
                        json.dumps(hr_data, ensure_ascii=False, indent=2),
                    )
            except Exception:
                pass

        done = self.global_done_chunks
        if done > 0 and done % 10 == 0:
            gc.collect()
            try:
                qs_path = self.checkpoint_dir / "quality_scores.json"
                qs_path.write_text(
                    json.dumps(self.shared_stats["quality_scores"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    except Exception:
        pass


# ── Glavni AI pipeline ────────────────────────────────────────────────────────

async def process_chunk_with_ai(self, chunk, prev_ctx, next_ctx, chunk_idx, file_name):
    """
    Obrađuje jedan HTML chunk kroz AI pipeline.

    V3.1 pipeline:
      1. Cache provjera
      2. AI prevođenje/lektura
      3. Kalkovi engine (Korak 2) — deterministička korekcija
      4. Morfo validator (Korak 3) — AI provjera glagola
      5. Quality scoring
      6. .chk upis
    """
    force_reprocess = getattr(self, "_force_reprocess", False)

    # ── Cache provjera ───────────────────────────────────────────────────────
    if not force_reprocess:
        cached_final = _chk_read(self, file_name, chunk_idx)
        if cached_final and _detektuj_en_ostatke(cached_final) < 0.08:
            from core.quality import _QUALITY_RESCUE_THRESHOLD
            qs = self.shared_stats.get("quality_scores", {})
            stem_key = f"{file_name}_blok_{chunk_idx}"
            raw_val = qs.get(stem_key, None)
            cached_score = _norm_score(raw_val) if raw_val is not None else None

            if cached_score is None or cached_score >= _QUALITY_RESCUE_THRESHOLD:
                score_info = f"score={cached_score:.1f}" if cached_score else "score=?"
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Učitan iz cache-a ({score_info}).",
                    "tech",
                )
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return cached_final, "DATABASE"
            else:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ♻️ Cache ignorisan "
                    f"(score={cached_score:.1f} < {_QUALITY_RESCUE_THRESHOLD}) — ponovo obrađujem.",
                    "warning",
                )

    # ── Setup ────────────────────────────────────────────────────────────────
    knjiga_mode = getattr(self, "knjiga_mode", None)
    if knjiga_mode is None:
        knjiga_mode = self._detect_language(chunk)

    rel_glosar = self._extract_relevant_glossary(chunk)
    tip_bloka = detektuj_tip_bloka(chunk)
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)

    # ════════════════════════════════════════════════════════════════════════
    # LEKTURA mod
    # ════════════════════════════════════════════════════════════════════════
    if knjiga_mode == "LEKTURA":

        if not force_reprocess:
            cached_lek = _chk_read(self, file_name, chunk_idx, "lektura")
            if cached_lek:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Lektura učitana iz cache-a.", "tech"
                )
                if not _chk_path(self, file_name, chunk_idx).exists():
                    _chk_write(self, file_name, chunk_idx, cached_lek)
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return cached_lek, "DATABASE/LEKTURA"

        sirovo = _automatska_korekcija(chunk)
        lek_sys = self._get_lektor_prompt(
            prev_kraj=prev_ctx,
            glosar_injekcija=rel_glosar,
            chapter_summary=chapter_summary,
            tip_bloka=tip_bloka,
        )
        p_lek = (
            f"IZVORNI TEKST (već na bosanskom/hrvatskom):\n{sirovo}\n\n"
            f"Lektoriraj tekst: ispravi interpunkciju, em-crtice u dijalogu, "
            f"stilske greške. NE PREVODI — tekst je već na HR/BS jeziku."
        )

        raw_l, prov_l = await self._call_ai_engine(
            p_lek, chunk_idx, uloga="LEKTOR",
            filename=file_name, sys_override=lek_sys, tip_bloka=tip_bloka,
        )

        if raw_l:
            finalno = _smart_extract(raw_l)
            if not finalno or _je_placeholder_lokalni(finalno):
                finalno = sirovo
        else:
            finalno = sirovo
            prov_l = "AUTO-HR"

        cist_priv = _agresivno_cisti(finalno)
        if not cist_priv or len(cist_priv.strip()) < 30:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Čišćenje dalo prazno – čuvam original.",
                "warning",
            )
            finalno = chunk
        else:
            finalno = _post_process_tipografija(cist_priv)

        finalno = _primijeni_kalkove_i_validator(self, finalno, file_name, chunk_idx)

        _chk_write(self, file_name, chunk_idx, finalno, "lektura")
        _chk_write(self, file_name, chunk_idx, finalno)

        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        gc.collect()
        self.log(f"[{file_name}] Blok {chunk_idx}: ✍️ HR lektura ({prov_l})", "tech")

        await _quality_scoring(
            self, finalno, None, chunk_idx, file_name,
            tip_bloka, f"LEKTURA/{prov_l}", tip_ocjenjivanja="lektura",
            prevodilac_provider=prov_l,
        )
        return finalno, f"LEKTURA/{prov_l}"

    # ════════════════════════════════════════════════════════════════════════
    # PREVOD mod
    # ════════════════════════════════════════════════════════════════════════

    sirovo_cached = None
    if not force_reprocess:
        sirovo_cached = _chk_read(self, file_name, chunk_idx, "prevod")
        if sirovo_cached:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ♻️ Sirovi prijevod iz cache-a — nastavljam od lektora.",
                "tech",
            )

    if sirovo_cached:
        sirovo = sirovo_cached
        prov1 = "DATABASE/PREVOD"
    else:
        fusion_sys = self._get_prevodilac_prompt(
            glosar_chunk=rel_glosar, prev_kraj=prev_ctx, tip_bloka=tip_bloka
        )
        p_fusion = f"Engleski tekst za prevod:\n{chunk}"
        raw_fusion, prov1 = await self._call_ai_engine(
            p_fusion, chunk_idx, uloga="PREVODILAC",
            filename=file_name, sys_override=fusion_sys, tip_bloka=tip_bloka,
        )
        if not raw_fusion:
            self.chunk_skips += 1
            return None, "N/A"

        sirovo = _agresivno_cisti(raw_fusion)
        _chk_write(self, file_name, chunk_idx, sirovo, "prevod")

    lek_sys = self._get_lektor_prompt(
        prev_kraj=prev_ctx,
        glosar_injekcija=rel_glosar,
        chapter_summary=chapter_summary,
        tip_bloka=tip_bloka,
    )
    p_lek = (
        f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
        f"SIROVI PRIJEVOD:\n{sirovo}\n\n"
        f"Profesionalno lektoriraj na bosanski/hrvatski."
    )
    raw_l, prov2 = await self._call_ai_engine(
        p_lek, chunk_idx, uloga="LEKTOR",
        filename=file_name, sys_override=lek_sys, tip_bloka=tip_bloka,
    )
    finalno = _smart_extract(raw_l) if raw_l else sirovo
    if not finalno:
        finalno = sirovo

    if _detektuj_en_ostatke(finalno) > 0.10:
        spas, _ = await _spasi_od_sirovog(
            self, sirovo, chunk, chunk_idx, file_name,
            prev_ctx, rel_glosar, "en>15%", tip_bloka,
        )
        if spas:
            finalno = spas

    if _detektuj_halucinaciju(chunk, finalno):
        self.log(f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju", "warning")

    finalno = _post_process_tipografija(_agresivno_cisti(finalno))
    finalno = _primijeni_kalkove_i_validator(self, finalno, file_name, chunk_idx)

    _chk_write(self, file_name, chunk_idx, finalno)
    try:
        _chk_path(self, file_name, chunk_idx, "prevod").unlink(missing_ok=True)
    except Exception:
        pass

    self.global_done_chunks += 1
    self.stvarno_prevedeno_u_sesiji += 1

    prov_label = f"{prov1}→{prov2}"
    await _quality_scoring(
        self, finalno, chunk, chunk_idx, file_name,
        tip_bloka, prov_label, tip_ocjenjivanja="prevod",
        prevodilac_provider=prov1,
    )

    # Korak 9 — Dinamički few-shot: dodaj dobar prijevod u BookContext
    if _BOOK_CTX_OK and getattr(self, "book_context", None):
        try:
            stem_key = f"{file_name}_blok_{chunk_idx}"
            qs_score = self.shared_stats.get("quality_scores", {}).get(stem_key, 0.0)
            if qs_score >= 8.5:
                en_tekst = BeautifulSoup(chunk, "html.parser").get_text()[:200]
                hr_tekst = BeautifulSoup(finalno, "html.parser").get_text()[:200]
                self.book_context.dodaj_few_shot_par(
                    originalni=en_tekst,
                    prevedeni=hr_tekst,
                    score=qs_score,
                )
        except Exception:
            pass

    aud = (
        f"📦 Blok {chunk_idx} [{tip_bloka}] | {prov1}→{prov2} | "
        f"EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:50]}… → "
        f"HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:50]}…"
    )
    self.log("", "accordion", en_text=aud)
    return finalno, f"{prov1}→{prov2}"


# ── Retry wrapper ─────────────────────────────────────────────────────────────

async def process_chunk_with_retry(
    self, chunk, prev_ctx, next_ctx, chunk_idx, file_name, max_retries=3
):
    """
    Obrađuje chunk sa ponavljanjem ako ne uspije.
    V3.1: Ispravan async poziv workers_v2 (WorkerV2 je sync klasa,
    pokreće se u executor-u da ne blokira event loop).
    """
    if USE_WORKERS_V2 and _V2_DOSTUPAN:
        self.log(
            f"[{file_name}] Blok {chunk_idx}: 🚀 V10.4 workers_v2 aktivan", "tech"
        )
        try:
            tip_bloka = detektuj_tip_bloka(chunk)
            rel_glosar = self._extract_relevant_glossary(chunk)
            chapter_summary = self._get_chapter_summary_for_lektor(file_name)

            worker = WorkerV2(
                uloga="prevodilac" if getattr(self, "knjiga_mode", "PREVOD") == "PREVOD"
                      else "lektor",
                tip_bloka=tip_bloka,
                book_context=getattr(self, "book_context", None),
                chapter_summary=chapter_summary,
            )

            # WorkerV2.obradi_chunk je sinkron — pokreni u thread pool-u
            loop = asyncio.get_event_loop()
            rezultat = await loop.run_in_executor(
                None,
                lambda: worker.obradi_chunk(chunk)
            )

            if rezultat and rezultat.get("success") and rezultat.get("tekst"):
                tekst = rezultat["tekst"]
                engine_label = (
                    f"V2/{rezultat.get('provider','?')}/{rezultat.get('model_ime','?')}"
                )
                if not hasattr(self, "_v2_engine_stats"):
                    self._v2_engine_stats = {}
                self._v2_engine_stats[f"{file_name}_blok_{chunk_idx}"] = engine_label

                # ── Korak 7: Zabilježi prevoditelja za nezavisni scorer ──
                if _SCORER_V2_OK and _zabilježi_prev:
                    try:
                        _zabilježi_prev(file_name, chunk_idx, engine_label)
                    except Exception:
                        pass

                # Upis checkpointa i quality scoringa
                _chk_write(self, file_name, chunk_idx, tekst)
                self.global_done_chunks += 1
                self.stvarno_prevedeno_u_sesiji += 1

                # Sačuvaj quality score iz V2
                stem_key = f"{file_name}_blok_{chunk_idx}"
                if not hasattr(self, "_quality_scores"):
                    self._quality_scores = {}
                if "quality_scores" not in self.shared_stats:
                    self.shared_stats["quality_scores"] = {}
                qs_raw = rezultat.get("quality_score", 0.0)
                qs = float(qs_raw) if qs_raw else 0.0
                # Ako V2 nije dao quality_score, pokreni nezavisni scorer
                if qs < 0.5:
                    try:
                        await _quality_scoring(
                            self, tekst, chunk, chunk_idx, file_name,
                            tip_bloka, engine_label,
                            tip_ocjenjivanja="prevod",
                            prevodilac_provider=engine_label,
                        )
                        qs = self.shared_stats.get("quality_scores", {}).get(stem_key, 0.0)
                    except Exception:
                        pass
                self._quality_scores[stem_key] = qs
                self.shared_stats["quality_scores"][stem_key] = qs

                return tekst, engine_label

            self.log(
                f"⚠️ [{file_name}] Blok {chunk_idx}: V2 nije vratio tekst — fallback na V1",
                "warning",
            )
        except Exception as v2_err:
            self.log(
                f"⚠️ [{file_name}] Blok {chunk_idx}: V2 iznimka "
                f"({type(v2_err).__name__}: {v2_err}) — fallback na V1",
                "warning",
            )

    # ── V1 fallback ──────────────────────────────────────────────────────────
    for attempt in range(max_retries):
        result, engine = await process_chunk_with_ai(
            self, chunk, prev_ctx, next_ctx, chunk_idx, file_name
        )
        if result is not None:
            return result, engine
        self.log(
            f"⚠️ Blok {chunk_idx} nije obrađen (pokušaj {attempt + 1}/{max_retries})",
            "warning",
        )
        if attempt < max_retries - 1:
            await asyncio.sleep(2)
            self.log("🔄 Pokušavam sa drugim modelom...", "info")

    self.log(
        f"❌ Blok {chunk_idx} nije obrađen ni nakon {max_retries} pokušaja — koristim original",
        "error",
    )
    return chunk, "ORIGINAL-FALLBACK"