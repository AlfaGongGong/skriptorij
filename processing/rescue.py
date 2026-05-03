

# processing/rescue.py
from core.text_utils import _smart_extract, _detektuj_en_ostatke, _detektuj_halucinaciju, _je_placeholder

async def _spasi_od_sirovog(self, sirovo, chunk, chunk_idx, file_name, prev_ctx, rel_glosar, razlog, tip_bloka="naracija"):
    PROV_REDOSLJED = ["GEMINI", "MISTRAL"]
    TEMP_LADDER = [0.60, 0.75]
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)
    lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar, chapter_summary=chapter_summary)
    p_lek = f"IZVORNI TEKST:\n{chunk}\n\nTEKST ZA LEKTURU (problem: {razlog}):\n{sirovo}\n\nAgresivno lektoriraj i vrati čist bosanski/hrvatski."

    for temp in TEMP_LADDER:
        for up in PROV_REDOSLJED:
            if up not in svi_upper: continue
            if self.shared_controls.get("stop"): return None, None
            m_name = self.fleet.get_active_model(up) if up != "GEMINI" else "gemini-2.0-flash"
            if not m_name: m_name = "default"
            raw_s, label_s = await self._call_single_provider(up, m_name, lek_sys, p_lek, temp, max_tokens=1200)
            if not raw_s: continue
            kand = _smart_extract(raw_s)
            if kand and not _je_placeholder(kand) and _detektuj_en_ostatke(kand) <= 0.12 and not _detektuj_halucinaciju(chunk, kand):
                self.log(f"[{file_name}] Blok {chunk_idx}: ✅ Spašeno ({label_s})", "info")
                return kand, label_s
    return None, None



