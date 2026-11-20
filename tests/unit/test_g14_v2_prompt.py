import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.prompts import get_model_patch_text
from processing.workers import WorkerV2

_BC = {"zanr": "fantasy", "ton": "mracan", "stil_pripovijedanja": "1. lice", "period": "srednji vijek"}


def test_prevodilac_dobiva_glosar_prethodni_kraj_i_sljedeci_kontekst():
    w = WorkerV2(
        uloga="prevodilac",
        tip_bloka="dijalog",
        book_context=_BC,
        chapter_summary="UPUTA: pripovjedac je Jorg, muski rod.",
        glosar_injekcija="Jorg Ancrath = Jorg Ancrath",
        prev_kraj="ZAVRSETAK PRETHODNOG BLOKA",
        next_kraj="\n\nKONTEKST (ne prevodi): sljedeci blok pocinje s ...abc...",
    )
    sp = w._sklopi_prompt("gemini_25_flash", "chunk")
    assert "Jorg Ancrath = Jorg Ancrath" in sp
    assert "ZAVRSETAK PRETHODNOG BLOKA" in sp
    assert "pripovjedac je Jorg" in sp
    assert "sljedeci blok pocinje" in sp
    assert "već preveden na HR" not in sp


def test_lektor_dobiva_kontekst_poglavlja_i_glosar():
    w = WorkerV2(
        uloga="lektor",
        tip_bloka="naracija",
        book_context=_BC,
        chapter_summary="SAZETAK POGLAVLJA XYZ",
        glosar_injekcija="Katherine = Katherine",
        prev_kraj="<p>prethodni kraj</p>",
    )
    sp = w._sklopi_prompt("gemini_25_flash", "chunk")
    assert "SAZETAK POGLAVLJA XYZ" in sp
    assert "Katherine = Katherine" in sp
    assert "prethodni kraj" in sp


def test_tip_bloka_none_i_nepoznat_ne_ruse():
    for tip in (None, "dark_fantasy", "horror_akcija"):
        w = WorkerV2(uloga="prevodilac", tip_bloka=tip, book_context=_BC)
        assert w._sklopi_prompt("nepoznati_model", "chunk").strip()


def test_bez_book_contexta_pada_na_stari_put_ali_vraca_prompt():
    w = WorkerV2(uloga="prevodilac", tip_bloka="naracija", book_context=None)
    assert w._sklopi_prompt("gemini_25_flash", "chunk").strip()


def test_model_patch_samo_anti_meta_i_markdown():
    t = get_model_patch_text("gemini_25_flash")
    assert t.strip()
    assert "STILSKE INSTRUKCIJE" not in t
    assert get_model_patch_text("nepostojeci_model_xyz") == "" or isinstance(
        get_model_patch_text("nepostojeci_model_xyz"), str
    )
