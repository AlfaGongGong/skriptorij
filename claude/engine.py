# core/engine.py
import re
import json
import time
import random
import shutil
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup
from api_fleet import FleetManager
from utils.logging import add_audit
from analysis.book_context import BookContextManager

class SkriptorijAllInOne:
    GLOSAR_UPDATE_INTERVAL = 5
    BATCH_SIZE = 1  # smanjeno za free tier

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
        self.work_dir = self.book_path.parent / f"_skr_{self.clean_book_name}"
        self.checkpoint_dir = self.work_dir / "checkpoints"
        self.out_path = self.book_path.parent / f"PREVEDENO_{self.clean_book_name}.epub"

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
        self._last_live_epub_time = 0.0

        self._quality_scores = {}
        self.pipeline_mode = "STANDARD"  # forsirano

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"V10.2 Engine inicijaliziran: {self.book_path.name} [STANDARD mod]", "tech")

    def log(self, msg, ltype="info", en_text=""):
        add_audit(msg, ltype, en_text, self.shared_stats)

    def _atomic_write(self, path, content):
        # ... isto kao prije ...
        pass

    def _detect_language(self, text):
        from core.text_utils import _detektuj_en_ostatke, _HR_DIACRITICALS
        cist = re.sub(r"<[^>]+>", "", text)
        if any(c in _HR_DIACRITICALS for c in cist):
            return "HR"
        return "EN" if _detektuj_en_ostatke(text) > 0.08 else "HR"

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
        return "Početak knjige ili kontekst nije dostupan."

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

    # Prompts metode delegirane u core.prompts
    def _get_prevodilac_prompt(self, glosar_chunk="", prev_kraj=""):
        from core.prompts import get_prevodilac_prompt
        return get_prevodilac_prompt(self.book_context, glosar_chunk or self.glosar_tekst, prev_kraj)

    def _get_lektor_prompt(self, prev_kraj="", glosar_injekcija="", chapter_summary=""):
        from core.prompts import get_lektor_prompt
        return get_lektor_prompt(self.book_context, prev_kraj, glosar_injekcija or self.glosar_tekst, chapter_summary)

    def _get_korektor_prompt(self):
        from core.prompts import KOREKTOR_TEMPLATE
        return KOREKTOR_TEMPLATE

    def _get_guardian_prompt(self):
        from core.prompts import GUARDIAN_SYS
        return GUARDIAN_SYS

    def _get_polish_prompt(self, tip_bloka="naracija"):
        from core.prompts import get_polish_prompt
        return get_polish_prompt(self.book_context, tip_bloka)

    # Chunking delegiran
    def chunk_html(self, html_content: str, max_words=800) -> list:
        from core.chunking import chunk_html
        return chunk_html(html_content, max_words)

    def get_context_window(self, chunks, idx, file_name):
        from core.chunking import get_context_window
        return get_context_window(self.checkpoint_dir, chunks, idx, file_name)

    # EPUB metode delegirane u epub modul
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

    # Mrežne metode delegirane
    async def _async_http_post(self, *args, **kwargs):
        from network.http_client import _async_http_post
        return await _async_http_post(self, *args, **kwargs)

    async def _call_single_provider(self, *args, **kwargs):
        from network.provider_router import _call_single_provider
        return await _call_single_provider(self, *args, **kwargs)

    async def _call_ai_engine(self, *args, **kwargs):
        from network.provider_router import _call_ai_engine
        return await _call_ai_engine(self, *args, **kwargs)

    # Pipeline metode
    async def process_chunk_with_ai(self, *args, **kwargs):
        from processing.pipeline import process_chunk_with_ai
        return await process_chunk_with_ai(self, *args, **kwargs)

    async def process_single_file_worker(self, *args, **kwargs):
        from processing.workers import process_single_file_worker
        return await process_single_file_worker(self, *args, **kwargs)

    # Analiza knjige
    async def analiziraj_knjigu(self, intro_text):
        from analysis.book_context import analiziraj_knjigu
        await analiziraj_knjigu(self, intro_text)

    async def _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime):
        from analysis.book_context import _inkrementalna_analiza_glosara
        await _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime)

    async def _generiraj_chapter_summary(self, file_name, file_content):
        from analysis.book_context import _generiraj_chapter_summary
        await _generiraj_chapter_summary(self, file_name, file_content)

    # Retro mod
    async def retroaktivna_relektura_v10(self, *args, **kwargs):
        from processing.retro import retroaktivna_relektura_v10
        await retroaktivna_relektura_v10(self, *args, **kwargs)