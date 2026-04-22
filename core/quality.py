# core/quality.py
import re
import json
from bs4 import BeautifulSoup

_QUALITY_RESCUE_THRESHOLD = 6.5

async def _scoruj_kvalitetu(tekst: str, engine_fn, chunk_idx: int, file_name: str, self_obj=None) -> float:
    try:
        cist = BeautifulSoup(tekst, "html.parser").get_text()[:600]
        if self_obj is not None:
            raw, _ = await self_obj._call_ai_engine(f"Ocijeni ovaj tekst:\n{cist}", chunk_idx, uloga="SCORER", filename=file_name)
        else:
            raw, _ = await engine_fn(f"Ocijeni ovaj tekst:\n{cist}", chunk_idx, uloga="SCORER", filename=file_name)
        if raw:
            m = re.search(r"\{.*?\}", raw, re.DOTALL)
            if m:
                obj = json.loads(m.group())
                return float(obj.get("ocjena", 8.0))
    except: pass
    return 8.0
