import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.routes.processing import _p26_ocisti


def test_prvi_redak_i_prefiks():
    assert _p26_ocisti("Prijevod: petnaest do dvanaest\nObjašnjenje...", "x") == "petnaest do dvanaest"


def test_odbija_prazno_isto_i_html():
    assert _p26_ocisti("", "a") == ""
    assert _p26_ocisti("isto", "isto") == ""
    assert _p26_ocisti("<b>x</b>", "a") == ""


def test_odbija_predugacak():
    assert _p26_ocisti("x " * 200, "kratko") == ""
