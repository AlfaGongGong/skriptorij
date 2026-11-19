"""G11 (lektor dobiva prev_kraj i sazetak), G12 (zatvarajuci navodnik U+201D), G13 (TOC prompt hrvatski)."""
from pathlib import Path

from core.prompts import get_lektor_prompt, get_toc_title_prompt, TOC_TITLE_SYS

BC = {"zanr": "fantasy", "ton": "mracan", "period": "srednji vijek"}


def test_lektor_dobiva_kontekst():
    p = get_lektor_prompt(BC, "<p>Prethodna zanimljiva recenica.</p>", "Gareth = Gareth", "Sazetak: bitka kod mosta.", "naracija")
    assert "Prethodna zanimljiva recenica." in p
    assert "<p>" not in p.split("PRETHODNI ODLOMAK")[1].split("\n")[0]
    assert "Sazetak: bitka kod mosta." in p
    assert "{prev_kraj}" not in p and "{chapter_summary}" not in p
    assert '{"finalno_polirano": "TEKST"}' in p


def test_lektor_prazan_kontekst():
    p = get_lektor_prompt(BC, "", "", "", "dijalog")
    assert "Nema chapter konteksta." in p


def test_sazetak_se_skracuje():
    p = get_lektor_prompt(BC, "x", "", "S" * 5000, "naracija")
    assert "S" * 501 not in p


def test_nema_u201c_kao_zatvaranja():
    src = Path("core/prompts.py").read_text("utf-8")
    assert "U+201C" not in src
    assert "U+201D" in src


def test_toc_prompt_hrvatski():
    assert "bosan" not in get_toc_title_prompt("Neki paragraf.").lower()
    assert "bosan" not in TOC_TITLE_SYS.lower()
