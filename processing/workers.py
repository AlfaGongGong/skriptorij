# processing/workers.py
import asyncio
import time
from bs4 import BeautifulSoup
from core.text_utils import _detektuj_en_ostatke
from processing.parallel import AdaptiveParallelism

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
            self.global_done_chunks += 1
            self.shared_stats["pct"] = int((self.global_done_chunks / self.global_total_chunks) * 100)
            self.shared_stats["ok"] = f"{self.global_done_chunks} / {self.global_total_chunks}"

    # Chapter summary
    cijelo_poglavlje = "".join(final_parts)
    await self._generiraj_chapter_summary(file_name, cijelo_poglavlje)

    body = orig_soup.body
    if body:
        body.clear()
        translated_soup = BeautifulSoup("".join(final_parts), "html.parser")
        for child in list(translated_soup.children):
            body.append(child.extract())
        file_path.write_text(str(orig_soup), encoding="utf-8")
    else:
        file_path.write_text("".join(final_parts), encoding="utf-8")
