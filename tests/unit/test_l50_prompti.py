"""L50-2: prompti traze dijalog u crticama, ne u navodnicima."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def _t(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_prompti_bez_dopustanja_navodnika_za_dijalog():
    p = _t("core/prompts.py")
    assert "\u00bbtekst\u00bb ili" not in p
    assert "Dijalog u navodnicima \u201e\u2026\u201d je ISPRAVAN" not in p
    assert "REPLIKE DIJALOGA" in p
    assert "ISKLJU\u010cIVO s em-crticom" in p


def test_workers_scorer_ne_hvali_navodnike():
    w = _t("processing/workers.py")
    assert "je ISPRAVAN i ne kaznjava se" not in w
    assert "replika s em-crticom" in w


def test_prompt_se_slaze():
    from core.prompts import get_system_prompt
    s = get_system_prompt("prevodilac", "gemini_25_flash", "dijalog")
    assert "em-crtic" in s and "NIKAD u navodnicima" in s
