"""
core/engine.py — SkriptorijAllInOne V10.2

IZMJENE (knjiga_mode patch + checkpoint putanja):
  - __init__(): self.work_dir i self.checkpoint_dir sada koriste
    CHECKPOINT_BASE_DIR/_skr_X umjesto book_path.parent/_skr_X.
    self.out_path ostaje u OUTPUT_DIR.
  - _detect_knjiga_mode() — analizira cijelu knjigu i vraća "PREVOD" / "LEKTURA".
  - _detect_language() zadržan kao interni helper.
"""

import re
import json
from pathlib import Path

from api_fleet import FleetManager
from utils.logging import add_audit
from analysis.book_context import BookContextManager
from config.settings import CHECKPOINT_BASE_DIR, OUTPUT_DIR


class SkriptorijAllInOne:
    GLOSAR_UPDATE_INTERVAL = 5
    BATCH_SIZE = 1

    def __init__(self, book_path, model_name, shared_stats, shared_controls):
        self.book_path = Path(book_path)
        self.model_name = model_name
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls
        self.fleet = FleetManager(config_path="dev_api.json")
        try:
            from api_fleet import register_active_fleet
            register_active_fleet(self.fleet)
        except Exception:
            pass

        self.clean_book_name = re.sub(r"[^a-zA-Z0-9_\-]", "", self.book_path.stem)

        # ── IZMJENA: work_dir i checkpoint_dir u CHECKPOINT_BASE_DIR ────────
        # Staro: self.book_path.parent / f"_skr_{self.clean_book_name}"
        # Novo:  CHECKPOINT_BASE_DIR  / f"_skr_{self.clean_book_name}"
        self.work_dir       = CHECKPOINT_BASE_DIR / f"_skr_{self.clean_book_name}"
        self.checkpoint_dir = self.work_dir / "checkpoints"

        # out_path ostaje u OUTPUT_DIR (Moon+ Reader biblioteka)
        self.out_path = OUTPUT_DIR / f"PREVEDENO_{self.clean_book_name}.epub"

        self.context_mgr = BookContextManager(self.checkpoint_dir, self.log)
        self.book_context = self.context_mgr.book_context
        self.knjiga_analizirana = False
        self.glosar_tekst = ""

        self._chapter_summaries = {}
        self._chapter_order = []
        self._last_live_epub_time = 0.0
        self._chapters_processed = 0

        self.toc_entries, self.chapter_counter = [], 0
        self.global_total_chunks = self.global_done_chunks = 0
        self.stvarno_prevedeno_u_sesiji = self.spaseno_iz_checkpointa = 0
        self.chunk_skips = 0
        self.html_files = []

        self._quality_scores = {}
        self.pipeline_mode = "STANDARD"

        # ── knjiga_mode: "PREVOD" | "LEKTURA" | None ─────────────────────────
        # Postavljeno od _detect_knjiga_mode() u run.py PRIJE main_loop.
        # None znači "nije još određeno" (pipeline čita self.knjiga_mode).
        self.knjiga_mode: str | None = None

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.log(
            f"V10.2 Engine inicijaliziran: {self.book_path.name} [STANDARD mod] "
            f"| checkpoint: {self.checkpoint_dir}",
            "tech",
        )

    # =========================================================================
    # LOGGING
    # =========================================================================

    def log(self, msg, ltype="info", en_text=""):
        add_audit(msg, ltype, en_text, self.shared_stats)

    # =========================================================================
    # I/O UTIL
    # =========================================================================

    def _atomic_write(self, path: Path, content: str) -> None:
        """Atomicno pisanje fajla — piše u .tmp pa zamjenjuje originalni."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        try:
            tmp.write_text(content, encoding='utf-8')
            tmp.replace(path)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            path.write_text(content, encoding='utf-8')
            self.log(f"[atomic_write] Fallback pisanje za {path.name}: {e}", "warning")

    # =========================================================================
    # DETEKCIJA JEZIKA — per-chunk (zadržan kao interni helper)
    # =========================================================================

    def _detect_language(self, text: str) -> str:
        """
        Brza per-chunk detekcija jezika za interne/fallback upotrebe.
        Vraća "HR" ili "EN".
        NAPOMENA: Za glavni pipeline koristi self.knjiga_mode (postavljeno jednom
                  za cijelu knjigu), ne ovaj metod.
        """
        from core.text_utils import _detektuj_en_ostatke, _HR_DIACRITICALS
        cist = re.sub(r"<[^>]+>", "", text)
        if any(c in _HR_DIACRITICALS for c in cist):
            return "HR"
        return "EN" if _detektuj_en_ostatke(text) > 0.08 else "HR"

    # =========================================================================
    # DETEKCIJA MODA KNJIGE — jednom za cijelu knjigu
    # =========================================================================

    def _detect_knjiga_mode(self, html_files: list, n_files: int = 5) -> str:
        """
        Analizira prvih N HTML fajlova knjige i određuje globalni mod obrade:

          "LEKTURA" — knjiga je već na bosanskom/hrvatskom (lektoriraj, ne prevodi)
          "PREVOD"  — knjiga je na engleskom (prevedi + lektoriraj)

        Algoritam:
          1. Konkatenira tekst prvih N fajlova (max 5000 znakova po fajlu)
          2. Računa % HR dijakritičkih znakova i EN stop-word postotak
          3. Odluka: ako je ≥60% sadržaja HR → "LEKTURA", inače → "PREVOD"

        Rezultat se sprema u self.knjiga_mode.
        """
        from core.text_utils import _detektuj_en_ostatke, _HR_DIACRITICALS
        from bs4 import BeautifulSoup

        uzorak_fajlova = html_files[:n_files]
        if not uzorak_fajlova:
            self.knjiga_mode = "PREVOD"
            return self.knjiga_mode

        ukupno_znakova = 0
        hr_znakova = 0
        svi_tekstovi = []

        for hf in uzorak_fajlova:
            try:
                sirovi = hf.read_text("utf-8", errors="ignore")
                tekst = BeautifulSoup(sirovi, "html.parser").get_text()[:5000]
                svi_tekstovi.append(tekst)
                ukupno_znakova += len(tekst)
                hr_znakova += sum(1 for c in tekst if c in _HR_DIACRITICALS)
            except Exception:
                continue

        if ukupno_znakova == 0:
            self.knjiga_mode = "PREVOD"
            return self.knjiga_mode

        kombinovano = "\n".join(svi_tekstovi)

        # Kriterij 1: HR dijakritika — jak signal
        hr_dijakritika_ratio = hr_znakova / max(1, ukupno_znakova)

        # Kriterij 2: EN stop-word postotak (iz text_utils)
        en_ratio = _detektuj_en_ostatke(kombinovano)

        # Odluka:
        # - Ako ima ikakve HR dijakritike (>0.3%) → LEKTURA
        # - Ili ako je EN stop-word ratio nizak (<8%) → LEKTURA
        # - Inače → PREVOD
        if hr_dijakritika_ratio > 0.003:
            mode = "LEKTURA"
        elif en_ratio < 0.08:
            mode = "LEKTURA"
        else:
            mode = "PREVOD"

        self.knjiga_mode = mode

        # Informiraj korisnika
        self.log(
            f"🔍 Detekcija knjige: mod=<b>{mode}</b> "
            f"(HR dijakritika={hr_dijakritika_ratio:.2%}, EN ratio={en_ratio:.2%}, "
            f"fajlova analizirano={len(uzorak_fajlova)})",
            "system"
        )
        # Spremi u shared_stats za UI prikaz
        self.shared_stats["knjiga_mode"] = mode
        self.shared_stats["knjiga_mode_info"] = (
            f"{mode} — {len(uzorak_fajlova)} fajl(ov)a analizirano "
            f"(HR={hr_dijakritika_ratio:.1%}, EN={en_ratio:.1%})"
        )

        return mode

    # =========================================================================
    # GLOSAR & KONTEKST
    # =========================================================================

    def _build_glosar_tekst(self):
        return self.context_mgr.build_glosar_tekst()

    def _extract_relevant_glossary(self, chunk_text):
        return self.context_mgr.extract_relevant_glossary(chunk_text, self.glosar_tekst)

    def _get_chapter_summary_for_lektor(self, current_file_name):
        try:
            idx = self._chapter_order.index(current_file_name)
            if idx > 0:
                prev_name = self._chapter_order[idx - 1]
                summary = self._chapter_summaries.get(prev_name, "")
                if summary:
                    return f"Prethodno poglavlje ({prev_name}): {summary}"
        except (ValueError, IndexError):
            pass
        return "Pocetak knjige ili kontekst nije dostupan."

    def _save_chapter_summaries(self):
        cache = self.checkpoint_dir / "chapter_summaries.json"
        data = {"summaries": self._chapter_summaries, "order": self._chapter_order}
        self._atomic_write(cache, json.dumps(data, ensure_ascii=False, indent=2))

    def _load_chapter_summaries(self):
        cache = self.checkpoint_dir / "chapter_summaries.json"
        if cache.exists():
            try:
                data = json.loads(cache.read_text("utf-8"))
                self._chapter_summaries = data.get("summaries", {})
                self._chapter_order = data.get("order", [])
            except Exception:
                pass

    # =========================================================================
    # PROMPT DELEGACIJA
    # =========================================================================

    def _get_prevodilac_prompt(self, glosar_chunk="", prev_kraj="", tip_bloka="naracija"):
        from core.prompts import get_prevodilac_prompt
        return get_prevodilac_prompt(
            self.book_context,
            glosar_chunk or self.glosar_tekst,
            prev_kraj,
            tip_bloka=tip_bloka,
        )

    def _get_lektor_prompt(self, prev_kraj="", glosar_injekcija="", chapter_summary="",
                           tip_bloka="naracija"):
        from core.prompts import get_lektor_prompt
        return get_lektor_prompt(
            self.book_context,
            prev_kraj,
            glosar_injekcija or self.glosar_tekst,
            chapter_summary,
            tip_bloka=tip_bloka,
        )

    def _get_korektor_prompt(self):
        from core.prompts import KOREKTOR_TEMPLATE
        return KOREKTOR_TEMPLATE

    def _get_guardian_prompt(self):
        from core.prompts import GUARDIAN_SYS
        return GUARDIAN_SYS

    def _get_polish_prompt(self, tip_bloka="naracija"):
        from core.prompts import get_polish_prompt
        return get_polish_prompt(self.book_context, tip_bloka)

    # =========================================================================
    # CHUNKING
    # =========================================================================

    def chunk_html(self, html_content: str, max_words=800) -> list:
        from core.chunking import chunk_html
        return chunk_html(html_content, max_words)

    def get_context_window(self, chunks, idx, file_name):
        from core.chunking import get_context_window
        return get_context_window(self.checkpoint_dir, chunks, idx, file_name)

    # =========================================================================
    # EPUB
    # =========================================================================

    def buildlive_epub(self):
        from epub.packager import buildlive_epub
        buildlive_epub(self)

    def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
        from epub.packager import apply_dropcap_and_toc
        apply_dropcap_and_toc(self, soup, html_file, samo_dropcap)

    def generate_ncx(self):
        from epub.packager import generate_ncx
        generate_ncx(self)

    def finalize(self):
        from epub.packager import finalize
        finalize(self)

    # =========================================================================
    # NETWORK
    # =========================================================================

    async def _async_http_post(self, *args, **kwargs):
        from network.http_client import _async_http_post
        return await _async_http_post(self, *args, **kwargs)

    async def _call_single_provider(self, *args, **kwargs):
        from network.provider_router import _call_single_provider
        return await _call_single_provider(self, *args, **kwargs)

    async def _call_ai_engine(self, *args, **kwargs):
        from network.provider_router import _call_ai_engine
        return await _call_ai_engine(self, *args, **kwargs)

    # =========================================================================
    # PIPELINE
    # =========================================================================

    async def process_chunk_with_ai(self, *args, **kwargs):
        from processing.pipeline import process_chunk_with_ai
        return await process_chunk_with_ai(self, *args, **kwargs)

    async def process_single_file_worker(self, *args, **kwargs):
        from processing.workers import process_single_file_worker
        return await process_single_file_worker(self, *args, **kwargs)

    # =========================================================================
    # ANALIZA KNJIGE
    # =========================================================================

    async def analiziraj_knjigu(self, intro_text):
        from analysis.book_context import analiziraj_knjigu
        await analiziraj_knjigu(self, intro_text)

    async def _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime):
        from analysis.book_context import _inkrementalna_analiza_glosara
        await _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime)

    async def _generiraj_chapter_summary(self, file_name, file_content):
        from analysis.book_context import _generiraj_chapter_summary
        await _generiraj_chapter_summary(self, file_name, file_content)

    # =========================================================================
    # RETRO RE-LEKTURA
    # =========================================================================


    # =========================================================================
    # CACHE MANAGEMENT — PATCH v1.0
    # =========================================================================

    def obrisi_cache(self, samo_losi: bool = False, threshold: float = None) -> int:
        """
        Briše .chk fajlove iz checkpoint_dir.

        samo_losi=False → briše sve .chk fajlove (potpuni reset)
        samo_losi=True  → briše samo fajlove čiji je score ispod threshold-a
        """
        from core.quality import _QUALITY_RESCUE_THRESHOLD
        threshold = threshold or _QUALITY_RESCUE_THRESHOLD
        chk_fajlovi = list(self.checkpoint_dir.glob("*.chk"))

        if not chk_fajlovi:
            self.log("ℹ️ Cache je prazan — nema .chk fajlova.", "info")
            return 0

        obrisano = 0

        if samo_losi:
            qs_cache = self.checkpoint_dir / "quality_scores.json"
            scores = {}
            if qs_cache.exists():
                try:
                    scores = json.loads(qs_cache.read_text("utf-8"))
                except Exception:
                    pass

            for chk in chk_fajlovi:
                score = scores.get(chk.stem, None)
                if score is not None and score < threshold:
                    try:
                        chk.unlink()
                        obrisano += 1
                    except Exception:
                        pass

            self.log(
                f"🧹 Obrisano {obrisano}/{len(chk_fajlovi)} loših .chk fajlova "
                f"(score < {threshold}).",
                "system",
            )
        else:
            for chk in chk_fajlovi:
                try:
                    chk.unlink()
                    obrisano += 1
                except Exception:
                    pass
            self.log(
                f"🗑️ Kompletan cache obrisan: {obrisano} .chk fajlova.", "system"
            )

        return obrisano

    def obrisi_cache_fajla(self, file_name: str) -> int:
        """Briše sve .chk fajlove koji pripadaju jednom HTML fajlu (poglavlju)."""
        pattern = f"{file_name}_blok_*.chk"
        chk_fajlovi = list(self.checkpoint_dir.glob(pattern))
        for chk in chk_fajlovi:
            try:
                chk.unlink()
            except Exception:
                pass
        self.log(
            f"🗑️ Cache fajla '{file_name}': {len(chk_fajlovi)} blokova obrisano.",
            "system",
        )
        return len(chk_fajlovi)

    def postavi_force_reprocess(self, aktivan: bool = True):
        """Postavi flag da pipeline ignorira cache za sve sljedeće blokove."""
        self._force_reprocess = aktivan
        if aktivan:
            self.log("⚡ force_reprocess=True — cache se ignorira za sve blokove.", "system")
        else:
            self.log("💾 force_reprocess=False — cache se koristi normalno.", "system")

    # ── RETRO / REVIZIJA delegacija ───────────────────────────────────────────

    async def mark_for_review(self, score_threshold: float = None):
        from processing.retro import mark_for_review
        return await mark_for_review(self, score_threshold or 6.5)

    async def send_to_fix(self, score_threshold: float = None):
        from processing.retro import send_to_fix
        return await send_to_fix(self, score_threshold or 6.5)

    async def retroaktivna_relektura_v10(self, *args, **kwargs):
        from processing.retro import retroaktivna_relektura_v10
        await retroaktivna_relektura_v10(self, *args, **kwargs)