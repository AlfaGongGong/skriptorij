# processing/pipeline.py
import re
import json
from bs4 import BeautifulSoup
from core.text_utils import (_smart_extract, _agresivno_cisti, _detektuj_en_ostatke,
                             _detektuj_halucinaciju, _post_process_tipografija,
                             _automatska_korekcija, _HR_DIACRITICALS)
from processing.rescue import _spasi_od_sirovog

async def process_chunk_with_ai(self, chunk, prev_ctx, next_ctx, chunk_idx, file_name):
    chk_fajl = self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"
    if chk_fajl.exists():
        try:
            zapamceno = chk_fajl.read_text("utf-8", errors="ignore")
            if len(zapamceno) > 10 and _detektuj_en_ostatke(zapamceno) < 0.08:
                self.log(f"[{file_name}] Blok {chunk_idx}: 💾 Učitan iz cache-a.", "tech")
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return zapamceno, "DATABASE"
        except Exception:
            pass

    jezik = self._detect_language(chunk)
    rel_glosar = self._extract_relevant_glossary(chunk)
    tip_bloka = "naracija"  # možemo dodati detekciju ako treba
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)

    if jezik == "HR":
        sirovo = _automatska_korekcija(chunk)
        finalno = _post_process_tipografija(sirovo)
        self._atomic_write(chk_fajl, finalno)
        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        return finalno, "AUTO-HR"

    # Fusion prevod (Groq/Cerebras)
    fusion_sys = self._get_prevodilac_prompt(glosar_chunk=rel_glosar, prev_kraj=prev_ctx)
    p_fusion = f"Engleski tekst za prevod:\n{chunk}"
    raw_fusion, prov1 = await self._call_ai_engine(p_fusion, chunk_idx, uloga="PREVODILAC",
                                                   filename=file_name, sys_override=fusion_sys)
    if not raw_fusion:
        self.chunk_skips += 1
        return None, "N/A"
    sirovo = _agresivno_cisti(raw_fusion)

    # Lektor (Gemini/Mistral/Gemma)
    lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar,
                                      chapter_summary=chapter_summary)
    p_lek = (f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
             f"SIROVI PRIJEVOD:\n{sirovo}\n\n"
             f"Profesionalno lektoriraj na bosanski/hrvatski.")
    raw_l, prov2 = await self._call_ai_engine(p_lek, chunk_idx, uloga="LEKTOR",
                                              filename=file_name, sys_override=lek_sys,
                                              tip_bloka=tip_bloka)
    finalno = _smart_extract(raw_l) if raw_l else sirovo
    if not finalno:
        finalno = sirovo

    # Provjera engleskog i halucinacije
    if _detektuj_en_ostatke(finalno) > 0.15:
        spas, _ = await _spasi_od_sirovog(self, sirovo, chunk, chunk_idx, file_name,
                                          prev_ctx, rel_glosar, "en>15%", tip_bloka)
        if spas:
            finalno = spas

    if _detektuj_halucinaciju(chunk, finalno):
        self.log(f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju", "warning")

    finalno = _post_process_tipografija(_agresivno_cisti(finalno))
    self._atomic_write(chk_fajl, finalno)
    self.global_done_chunks += 1
    self.stvarno_prevedeno_u_sesiji += 1

    # Audit log
    aud = (f"📦 Blok {chunk_idx} | {prov1}→{prov2} | "
           f"EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:50]}… → "
           f"HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:50]}…")
    self.log("", "accordion", en_text=aud)
    return finalno, f"{prov1}→{prov2}"