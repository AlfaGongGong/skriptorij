# processing/retro.py
# BUGFIX:
#   B10: Retro ne smije čitati .prevod.chk i .lektura.chk međukorak fajlove —
#        sada iterira SAMO finalne .chk fajlove (bez tačke u stem-u iza _blok_N).
#   B11: old_text se čistio raw HTML direktno u prompt — sada BeautifulSoup strip.
#   B12: GUARDIAN + POLISH pozivi bili bezuvjetni — sada samo ako lektor poboljšao.
#   B13: checkpoint_dir se nalazio u work_dir — sada koristi CHECKPOINT_BASE_DIR.
#   B14: mark_for_review iterirala sve *.chk uključujući međukorak fajlove.

import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from core.text_utils import (
    _agresivno_cisti,
    _post_process_tipografija,
    _detektuj_halucinaciju,
    _detektuj_en_ostatke,
)
from core.quality import _scoruj_kvalitetu, _QUALITY_RESCUE_THRESHOLD


def _je_finalni_chk(chk_path: Path) -> bool:
    """
    B10 FIX: Razlikuje finalne .chk od međukorak fajlova.

    Finalni:    chapter001.html_blok_0.chk       → stem = chapter001.html_blok_0
    Međukorak:  chapter001.html_blok_0.prevod.chk → stem = chapter001.html_blok_0.prevod
                chapter001.html_blok_0.lektura.chk
    """
    # Ako stem (bez .chk) sadrži ".prevod" ili ".lektura" → međukorak
    stem = chk_path.stem  # npr. "chapter001.html_blok_0" ili "chapter001.html_blok_0.prevod"
    return not (stem.endswith(".prevod") or stem.endswith(".lektura"))


def _get_checkpoint_dir(self) -> Path:
    """
    B13 FIX: Uvijek koristi centralni CHECKPOINT_BASE_DIR, ne work_dir/checkpoints.
    """
    # Ako engine već ima checkpoint_dir (normalni tok), koristi ga
    if hasattr(self, "checkpoint_dir") and self.checkpoint_dir.exists():
        return self.checkpoint_dir
    # Fallback: izgradi iz CHECKPOINT_BASE_DIR
    from config.settings import CHECKPOINT_BASE_DIR
    clean_name = getattr(self, "clean_book_name", "knjiga")
    return CHECKPOINT_BASE_DIR / f"_skr_{clean_name}" / "checkpoints"


async def retroaktivna_relektura_v10(
    self, target_work_dir=None, force=False, only_bad=False,
    bad_threshold=_QUALITY_RESCUE_THRESHOLD, stems_whitelist=None
):
    """
    B10 FIX: Iterira samo finalne .chk fajlove (ne međukorak fajlove).
    B11 FIX: Čisti HTML iz old_text prije slanja u AI prompt.
    B12 FIX: GUARDIAN i POLISH se pozivaju samo ako lektor stvarno poboljšao tekst.
    B13 FIX: checkpoint_dir dolazi iz _get_checkpoint_dir() (centralni).
    """
    if target_work_dir:
        self.work_dir = Path(target_work_dir)

    chk_dir = _get_checkpoint_dir(self)
    self.checkpoint_dir = chk_dir  # ažuriraj engine atribut

    # B10 FIX: samo finalni .chk fajlovi
    svi_chk = sorted(
        [f for f in chk_dir.glob("*.chk") if _je_finalni_chk(f)]
    )

    if not svi_chk:
        self.log("❌ Nema finalnih .chk fajlova.", "error")
        return

    # ── Selektivni mod ───────────────────────────────────────────────────────
    if stems_whitelist is not None:
        whiteset = set(stems_whitelist)
        ciljani = [chk for chk in svi_chk if chk.stem in whiteset]
        nedostaju = whiteset - {chk.stem for chk in ciljani}
        if nedostaju:
            self.log(
                f"⚠️ Neki označeni blokovi nemaju .chk fajl: {sorted(nedostaju)}",
                "warning",
            )
    elif force:
        ciljani = svi_chk
    elif only_bad:
        qs_cache = chk_dir / "quality_scores.json"
        prev_scores = {}
        if qs_cache.exists():
            try:
                prev_scores = json.loads(qs_cache.read_text("utf-8"))
            except Exception:
                pass
        ciljani = [
            chk for chk in svi_chk
            if prev_scores.get(chk.stem, 10.0) < bad_threshold
        ]
    else:
        ciljani = svi_chk

    self.log(
        f"🔄 Retro re-lektura: {len(ciljani)}/{len(svi_chk)} blokova",
        "system",
    )

    if not hasattr(self, "_quality_scores"):
        self._quality_scores = {}

    for chk in ciljani:
        if self.shared_controls.get("stop"):
            break

        old_text_raw = chk.read_text("utf-8", errors="ignore")

        # B11 FIX: Čisti HTML za AI prompt, ali čuva originalni HTML za upis
        try:
            old_text_cist = BeautifulSoup(old_text_raw, "html.parser").get_text(
                separator="\n", strip=True
            )
        except Exception:
            old_text_cist = re.sub(r"<[^>]+>", " ", old_text_raw).strip()

        file_name = (
            chk.stem.split("_blok_")[0] if "_blok_" in chk.stem else "retro"
        )
        chunk_idx_str = (
            chk.stem.split("_blok_")[-1] if "_blok_" in chk.stem else "0"
        )
        try:
            chunk_idx = int(chunk_idx_str)
        except ValueError:
            chunk_idx = 0

        rel_glosar = self._extract_relevant_glossary(old_text_cist)
        chapter_summary = self._get_chapter_summary_for_lektor(file_name)
        tip_bloka = "naracija"  # retro uvijek naracija (sigurno, nema HTML za detekciju)

        lek_sys = self._get_lektor_prompt(
            prev_kraj="",
            glosar_injekcija=rel_glosar,
            chapter_summary=chapter_summary,
            tip_bloka=tip_bloka,
        )
        # B11 FIX: šalje čisti tekst, ne sirovi HTML
        p_lek = f"Lektoriraj tekst:\n{old_text_cist}"
        raw_l, _ = await self._call_ai_engine(
            p_lek, chunk_idx, uloga="LEKTOR",
            filename=file_name, sys_override=lek_sys, tip_bloka=tip_bloka,
        )
        finalno = _agresivno_cisti(raw_l) if raw_l else old_text_raw

        # B12 FIX: GUARDIAN i POLISH samo ako lektor zaista nešto promijenio
        # i ako tekst nije haluciniran
        lektor_promjenio = raw_l and (finalno.strip() != old_text_cist.strip())
        lektor_halucinacija = _detektuj_halucinaciju(old_text_cist, finalno, "LEKTOR")

        if lektor_promjenio and not lektor_halucinacija:
            guard_raw, _ = await self._call_ai_engine(
                finalno, chunk_idx, uloga="GUARDIAN", filename=file_name
            )
            if guard_raw:
                g_cist = _agresivno_cisti(guard_raw)
                # Prihvati guardian samo ako nije halucinacija
                if not _detektuj_halucinaciju(finalno, g_cist, "LEKTOR"):
                    finalno = g_cist

            # POLISH samo ako je lektor + guardian prošao validaciju
            polish_raw, _ = await self._call_ai_engine(
                finalno, chunk_idx, uloga="POLISH", filename=file_name
            )
            if polish_raw:
                p_cist = _agresivno_cisti(polish_raw)
                if not _detektuj_halucinaciju(finalno, p_cist, "LEKTOR"):
                    finalno = p_cist
        elif not lektor_promjenio:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ℹ️ Lektor nije promijenio tekst — "
                f"GUARDIAN/POLISH preskočeni.",
                "tech",
            )
        elif lektor_halucinacija:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Halucinacija detekovana — "
                f"čuvam originalni tekst.",
                "warning",
            )
            finalno = old_text_raw  # vrati original ako halucinacija

        # Quality scoring s relektura penalizacijom
        ocjena = await _scoruj_kvalitetu(
            finalno,
            self._call_ai_engine,
            chunk_idx,
            file_name,
            self_obj=self,
            stari_tekst=old_text_raw,
            tip_ocjenjivanja="relektura",
        )

        if ocjena is None or not isinstance(ocjena, (int, float)):
            from core.quality import _izracunaj_heuristicki_score
            ocjena, _ = _izracunaj_heuristicki_score(finalno)

        ocjena = round(float(max(1.0, min(10.0, ocjena))), 1)

        self._quality_scores[chk.stem] = ocjena
        if "quality_scores" not in self.shared_stats:
            self.shared_stats["quality_scores"] = {}
        self.shared_stats["quality_scores"][chk.stem] = ocjena

        finalno = _post_process_tipografija(finalno)
        self._atomic_write(chk, finalno)
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ✅ Retro | score: {ocjena:.1f}/10",
            "info",
        )

    # ── Spremi scores na disk ────────────────────────────────────────────────
    qs_cache = chk_dir / "quality_scores.json"
    existing_scores = {}
    if qs_cache.exists():
        try:
            existing_scores = json.loads(qs_cache.read_text("utf-8"))
        except Exception:
            pass
    existing_scores.update(self._quality_scores)

    cleaned_scores = {}
    for k, v in existing_scores.items():
        if isinstance(v, dict) and "score" in v:
            cleaned_scores[k] = float(v["score"])
        elif isinstance(v, (int, float)) and v is not None:
            cleaned_scores[k] = float(v)

    self._atomic_write(
        qs_cache,
        json.dumps(cleaned_scores, ensure_ascii=False, indent=2),
    )

    # Finalizacija
    html_files = getattr(self, "html_files", [])
    for hf in html_files:
        try:
            soup = BeautifulSoup(hf.read_text("utf-8"), "html.parser")
            self.apply_dropcap_and_toc(soup, hf)
            hf.write_text(str(soup), encoding="utf-8")
        except Exception:
            pass

    self.generate_ncx()
    self.finalize()
    self.log("🎉 Retro obrada završena!", "system")


async def mark_for_review(self, score_threshold: float = _QUALITY_RESCUE_THRESHOLD):
    """
    B14 FIX: Iterira samo finalne .chk fajlove (ne .prevod.chk, .lektura.chk).
    """
    chk_dir = _get_checkpoint_dir(self)
    review_list = []

    qs_cache = chk_dir / "quality_scores.json"
    scores = {}
    if qs_cache.exists():
        try:
            raw = json.loads(qs_cache.read_text("utf-8"))
            for k, v in raw.items():
                if isinstance(v, (int, float)):
                    scores[k] = float(v)
                elif isinstance(v, dict) and "score" in v:
                    scores[k] = float(v["score"])
        except Exception:
            pass

    # B14 FIX: samo finalni fajlovi
    finalni_chk = [f for f in sorted(chk_dir.glob("*.chk")) if _je_finalni_chk(f)]

    for chk_file in finalni_chk:
        try:
            text = chk_file.read_text("utf-8")
            needs_review = False
            reason = []

            qs = scores.get(chk_file.stem, None)
            if qs is not None and qs < score_threshold:
                needs_review = True
                reason.append(f"Score: {qs:.1f}/10")

            en_score = _detektuj_en_ostatke(text)
            if en_score > 0.05:
                needs_review = True
                reason.append(f"Engleski ostatak: {en_score:.0%}")

            if len(text.strip()) < 50:
                needs_review = True
                reason.append("Prekratak tekst")

            if '"' in text and "\u2014" not in text:
                dijalog_glagoli = any(
                    g in text.lower()
                    for g in ["reče", "rekla", "rekao", "upita", "odgovori", "viknu"]
                )
                if dijalog_glagoli:
                    needs_review = True
                    reason.append("Dijalog bez em-crtice")

            if needs_review:
                review_list.append({
                    "file":    chk_file.name,
                    "stem":    chk_file.stem,
                    "score":   qs,
                    "reason":  ", ".join(reason),
                    "preview": BeautifulSoup(text, "html.parser").get_text()[:120] + "...",
                })
        except Exception:
            pass

    review_path = chk_dir / "human_review.json"
    self._atomic_write(
        review_path,
        json.dumps(review_list, ensure_ascii=False, indent=2),
    )
    self.log(
        f"📋 {len(review_list)} chunkova označeno za reviziju "
        f"(od {len(finalni_chk)} finalnih .chk fajlova)",
        "system",
    )
    return review_list


async def send_to_fix(self, score_threshold: float = _QUALITY_RESCUE_THRESHOLD):
    """
    Automatski ispravlja blokove s lošim scoreom.
    """
    chk_dir = _get_checkpoint_dir(self)

    qs_cache = chk_dir / "quality_scores.json"
    scores = {}
    if qs_cache.exists():
        try:
            raw = json.loads(qs_cache.read_text("utf-8"))
            for k, v in raw.items():
                if isinstance(v, (int, float)):
                    scores[k] = float(v)
                elif isinstance(v, dict) and "score" in v:
                    scores[k] = float(v["score"])
        except Exception:
            pass

    # B14 FIX: samo finalni fajlovi
    losi = [
        chk for chk in sorted(chk_dir.glob("*.chk"))
        if _je_finalni_chk(chk)
        and scores.get(chk.stem, 10.0) < score_threshold
    ]

    if not losi:
        self.log(
            f"✅ Nema blokova s scoreom < {score_threshold} — ništa za ispraviti.",
            "info",
        )
        return 0

    self.log(
        f"🔧 send_to_fix: {len(losi)} blokova s lošim scoreom → brišem cache + retro obrada",
        "system",
    )

    for chk in losi:
        try:
            chk.unlink()
        except Exception as e:
            self.log(f"⚠️ Nisam uspio obrisati {chk.name}: {e}", "warning")

    await retroaktivna_relektura_v10(
        self, force=True, only_bad=False, bad_threshold=score_threshold
    )

    return len(losi)