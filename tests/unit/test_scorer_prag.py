import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import quality as Q

TEKST = ("<p>Vjetar je šaptao kroz stare hrastove dok smo se probijali prema selu. "
         "Nitko od nas nije govorio, jer je svaki zvuk mogao otkriti gdje se nalazimo. "
         "Kad smo napokon ugledali dim iznad krovova, Makin je zastao i pogledao me.</p>"
         "<p>„Mislim da nas čekaju”, rekao je tiho. „Pa neka čekaju”, odgovorio sam.</p>")


def test_prompt_ima_napomenu_o_isjecku():
    uhvaceno = {}

    async def fn(prompt, idx, uloga=None, filename=None):
        uhvaceno["p"] = prompt
        return '{"ocjena": 9.0, "kriteriji": {"tacnost": 9}, "razlog": "ok"}', "GROQ"

    meta = {}
    asyncio.run(Q._scoruj_kvalitetu(TEKST, fn, 0, "f.html", tip_ocjenjivanja="prevod", meta_out=meta))
    assert "ISJECAK" in uhvaceno["p"]
    assert "TEKST ZA OCJENU" in uhvaceno["p"]
    assert meta.get("ai") == 9.0


def test_prag_je_8():
    assert Q._QUALITY_RESCUE_THRESHOLD == 8.0
    assert Q._CACHE_ACCEPT_SCORE < Q._QUALITY_RESCUE_THRESHOLD
