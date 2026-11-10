import re
from core.engine import SkriptorijAllInOne

EN = "A lot of animals will decide to complain, the Count’s men saw decency in the Field. You’re to the Field? Before I could decide."

def test_en_blok_je_prevod():
    assert SkriptorijAllInOne._detect_language(None, EN) == "PREVOD"

def test_guard_u_pipelineu():
    s = open("processing/pipeline.py", encoding="utf-8").read()
    assert "P2.13 EN guard" in s and 'self._detect_language(chunk) == "PREVOD"' in s

def test_dece_deci_ne_hvata_decide():
    import importlib
    for m in ("core.kalkovi.dinamicki_detektor", "core.kalkovi.dinamicki_lista"):
        mod = importlib.import_module(m)
        for an in dir(mod):
            v = getattr(mod, an)
            if isinstance(v, (list, tuple)):
                for x in v:
                    if isinstance(x, (list, tuple)) and len(x) >= 2 and isinstance(x[0], str) and isinstance(x[1], str) and x[0] in ("dece", "deci") or (isinstance(x, (list, tuple)) and x and isinstance(x[0], str) and x[0].endswith(("dece\\b", "deci\\b"))):
                        assert re.sub(x[0], x[1], "decide decency") == "decide decency"
