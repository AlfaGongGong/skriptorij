
# processing/rescue.py
from core.text_utils import _smart_extract, _detektuj_en_ostatke, _detektuj_halucinaciju, _je_placeholder

async def _spasi_od_sirovog(self, sirovo, chunk, chunk_idx, file_name, prev_ctx, rel_glosar, razlog, tip_bloka="naracija"):
    # Redosljed provajdera — GEMINI nije uvijek prvi.
    # Ako je Gemini upravo vratio grešku (u cooldownu), počinjemo s drugima.
    # Dinamički sortiramo: dostupni ključevi idu prvi, ostali iza.
    _BASE_REDOSLJED = ["GEMINI", "CEREBRAS", "GROQ", "COHERE", "MISTRAL"]
    TEMP_LADDER = [0.55, 0.70, 0.80]
    svi_upper = {p.upper() for p in self.fleet.fleet.keys()}

    # Sortiraj po dostupnosti — provajderi s dostupnim ključevima idu prvi
    def _prov_dostupan(prov):
        try:
            keys = self.fleet.fleet.get(prov, [])
            return any(ks.available for ks in keys)
        except Exception:
            return False

    PROV_REDOSLJED = sorted(
        [p for p in _BASE_REDOSLJED if p in svi_upper],
        key=lambda p: (0 if _prov_dostupan(p) else 1)
    )

    chapter_summary = self._get_chapter_summary_for_lektor(file_name)
    lek_sys = self._get_lektor_prompt(prev_kraj=prev_ctx, glosar_injekcija=rel_glosar, chapter_summary=chapter_summary, tip_bloka=tip_bloka)
    p_lek = (
        f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
        f"TEKST ZA POPRAVAK (problem: {razlog}):\n{sirovo}\n\n"
        "ZADATAK: Agresivno lektoriraj — prevedi SVE engleske ostatke, ispravi kalkove, "
        "vrati cist bosanski/hrvatski. Obavezno ijekavica. Navodnici: \u201eovako\u201c. "
        "Dijalog: \u2014 em-crtica. Glagol+da+prezent \u2192 infinitiv.\n"
        "Vrati ISKLJUCIVO JSON: {\"finalno_polirano\": \"TEKST\"}"
    )

    for temp in TEMP_LADDER:
        for up in PROV_REDOSLJED:
            if self.shared_controls.get("stop"):
                return None, None
            # Gemini: koristi aktivan model iz poola, ne hardkodirani 2.0-flash
            m_name = self.fleet.get_active_model(up)
            if not m_name:
                continue
            raw_s, label_s = await self._call_single_provider(up, m_name, lek_sys, p_lek, temp, max_tokens=1400)
            if not raw_s:
                continue
            kand = _smart_extract(raw_s)
            if (kand and not _je_placeholder(kand)
                    and _detektuj_en_ostatke(kand) <= 0.08
                    and not _detektuj_halucinaciju(chunk, kand)):
                self.log(f"[{file_name}] Blok {chunk_idx}: ✅ Spašeno ({label_s}, temp={temp})", "info")
                return kand, label_s
    return None, None



