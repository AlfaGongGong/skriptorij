import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import quality as Q

R1 = '{"ocjena": 9.25, "kriteriji": {"tacnost": 9, "jezik": 9, "stil": 10, "tipografija": 9}, "razlog": "Tekst je idiomatski."}'
R2 = '{\n"ocjena": 8.5,\n"kriteriji": {\n"tacnost": 9,\n"jezik": 8,\n"stil": 9,\n"tipografija": 8\n},\n"razlog": "Dobro."\n}'
R3 = '{"ocjena": 8.5, "kriteriji": {"tacnost": 9, "jezik": 8}, "razlog": "predugo razmisljanje \'prstiju\' je rij'
R4 = 'Evo ocjene: {"ocjena": 7.0, "kriteriji": {"tacnost": 7}, "razlog": "ok"} hvala'

TEKST = ("<p>Vjetar je šaptao kroz stare hrastove dok smo se probijali prema selu. "
         "Nitko od nas nije govorio, jer je svaki zvuk mogao otkriti gdje se nalazimo. "
         "Kad smo napokon ugledali dim iznad krovova, Makin je zastao i pogledao me.</p>"
         "<p>„Mislim da nas čekaju”, rekao je tiho. „Pa neka čekaju”, odgovorio sam.</p>")


def _o(raw):
    import json
    m = Q._scorer_json_match(raw)
    return json.loads(m.group()).get("ocjena") if m else None


def test_stvarni_odgovori():
    assert _o(R1) == 9.25
    assert _o(R2) == 8.5
    assert _o(R3) == 8.5
    assert _o(R4) == 7.0
    assert _o("nema nikakvog jsona") is None


def test_scoruj_kvalitetu_dobije_ai_ocjenu():
    async def fn(prompt, idx, uloga=None, filename=None):
        return R1, "GROQ"
    meta = {}
    s = asyncio.run(Q._scoruj_kvalitetu(TEKST, fn, 0, "f.html", tip_ocjenjivanja="prevod", meta_out=meta))
    assert meta.get("ai") == 9.25, meta
    assert meta.get("status") != "heur_only", meta
