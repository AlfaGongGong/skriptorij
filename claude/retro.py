# processing/retro.py
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from core.text_utils import _agresivno_cisti, _post_process_tipografija, _detektuj_halucinaciju
from core.quality import _scoruj_kvalitetu, _QUALITY_RESCUE_THRESHOLD

async def retroaktivna_relektura_v10(self, target_work_dir=None, force=False, only_bad=False, bad_threshold=_QUALITY_RESCUE_THRESHOLD):
    if target_work_dir:
        self.work_dir = Path(target_work_dir)
    self.checkpoint_dir = self.work_dir / "checkpoints"
    chk_files = sorted(list(self.checkpoint_dir.glob("*.chk")))
    if not chk_files:
        self.log("❌ Nema .chk fajlova.", "error")
        return

    # Odabir blokova prema modu
    if force:
        ciljani = chk_files
    elif only_bad:
        qs_cache = self.checkpoint_dir / "quality_scores.json"
        prev_scores = {}
        if qs_cache.exists():
            try: prev_scores = json.loads(qs_cache.read_text("utf-8"))
            except: pass
        ciljani = [chk for chk in chk_files if prev_scores.get(chk.stem, 10.0) < bad_threshold]
    else:
        ciljani = chk_files

    self.log(f"🔄 Retro re-lektura: {len(ciljani)}/{len(chk_files)} blokova", "system")

    for chk in ciljani:
        if self.shared_controls.get("stop"): break
        old_text = chk.read_text("utf-8", errors="ignore")
        file_name = chk.stem.split("_blok_")[0] if "_blok_" in chk.stem else "retro"
        chunk_idx = int(chk.stem.split("_blok_")[-1]) if "_blok_" in chk.stem else 0
        tip_bloka = "naracija"
        rel_glosar = self._extract_relevant_glossary(old_text)
        chapter_summary = self._get_chapter_summary_for_lektor(file_name)

        lek_sys = self._get_lektor_prompt(prev_kraj="", glosar_injekcija=rel_glosar, chapter_summary=chapter_summary)
        p_lek = f"Lektoriraj tekst:\n{old_text}"
        raw_l, _ = await self._call_ai_engine(p_lek, chunk_idx, uloga="LEKTOR", filename=file_name, sys_override=lek_sys, tip_bloka=tip_bloka)
        finalno = _agresivno_cisti(raw_l) if raw_l else old_text

        # Guardian i Polish (opciono)
        guard_raw, _ = await self._call_ai_engine(finalno, chunk_idx, uloga="GUARDIAN", filename=file_name)
        if guard_raw: finalno = _agresivno_cisti(guard_raw)
        polish_raw, _ = await self._call_ai_engine(finalno, chunk_idx, uloga="POLISH", filename=file_name)
        if polish_raw: finalno = _agresivno_cisti(polish_raw)

        ocjena = await _scoruj_kvalitetu(finalno, self._call_ai_engine, chunk_idx, file_name, self_obj=self)
        self._quality_scores[chk.stem] = ocjena

        finalno = _post_process_tipografija(finalno)
        self._atomic_write(chk, finalno)
        self.log(f"[{file_name}] Blok {chunk_idx}: ✅ Retro | score: {ocjena:.1f}/10", "info")

    # Sačuvaj quality scores
    qs_cache = self.checkpoint_dir / "quality_scores.json"
    self._atomic_write(qs_cache, json.dumps(self._quality_scores, ensure_ascii=False, indent=2))

    # Rebuild EPUB
    for hf in self.html_files:
        try:
            soup = BeautifulSoup(hf.read_text("utf-8"), "html.parser")
            self.apply_dropcap_and_toc(soup, hf)
            hf.write_text(str(soup), encoding="utf-8")
        except: pass
    self.generate_ncx()
    self.finalize()
    self.log("🎉 Retro obrada završena!", "system")
