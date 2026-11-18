"""L58 DIO 1: smoke test pipelinea (process_chunk_with_ai) s lazim providerom.

Bez mreze: _call_ai_engine je zamijenjen lazom; FleetManager i model discovery su stubovi;
checkpointi idu u tmp_path.
"""
import asyncio
import zipfile
from pathlib import Path

import pytest

EN_CHUNK = (
    "<p>The old man walked slowly down the road, and the wind was cold against his face. "
    "He had not seen his brother for many years, and he did not know what he would say.</p>"
)
HR_PREVOD = (
    "<p>Starac je polako hodao cestom, a vjetar mu je hladno puhao u lice. "
    "Nije vidio brata godinama i nije znao što će mu reći.</p>"
)


class _LazniFleet:
    fleet = {}

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def engine(tmp_path, monkeypatch):
    import core.engine as eng

    monkeypatch.setattr(eng, "CHECKPOINT_BASE_DIR", tmp_path / "cp")
    monkeypatch.setattr(eng, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(eng, "FleetManager", _LazniFleet)
    import network.model_discovery as md

    monkeypatch.setattr(md, "start_background_discovery", lambda *a, **k: None)
    epub = tmp_path / "Mala_Knjiga.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    stats = {"quality_scores": {}}
    e = eng.SkriptorijAllInOne(str(epub), "test", stats, {"stop": False})
    e.knjiga_mode = "PREVOD"
    e.poziva = []
    return e


def _lazni(e, odgovori):
    """odgovori: funkcija (uloga, prompt) -> (raw, provider)."""

    async def _call(prompt, chunk_idx, *a, uloga="", **k):
        e.poziva.append(uloga)
        return odgovori(uloga, prompt)

    e._call_ai_engine = _call


def test_prijevod_ide_kroz_pipeline_i_upisuje_chk(engine):
    _lazni(engine, lambda u, p: (HR_PREVOD, "LAZNI"))
    res, tag = asyncio.run(
        engine.process_chunk_with_ai(EN_CHUNK, "", "", 0, "chapter001.html")
    )
    assert res and "Starac" in res
    assert "The old man" not in res
    assert engine.poziva, "provider nije pozvan"
    chk = list(Path(engine.checkpoint_dir).glob("*.chk"))
    assert chk, "nije upisan nijedan .chk"


def test_drugi_poziv_cita_cache_bez_providera(engine):
    _lazni(engine, lambda u, p: (HR_PREVOD, "LAZNI"))
    asyncio.run(engine.process_chunk_with_ai(EN_CHUNK, "", "", 0, "chapter001.html"))
    n = len(engine.poziva)
    res, tag = asyncio.run(
        engine.process_chunk_with_ai(EN_CHUNK, "", "", 0, "chapter001.html")
    )
    assert len(engine.poziva) == n, "cache nije iskoristen"
    assert tag == "DATABASE"
    assert "Starac" in res


def test_provider_pada_nikad_ne_vraca_en_kao_prijevod(engine):
    _lazni(engine, lambda u, p: (None, ""))
    res, tag = asyncio.run(
        engine.process_chunk_with_ai(EN_CHUNK, "", "", 0, "chapter001.html")
    )
    # smije vratiti None ili marker, ali ne goli EN original kao uspjeh
    assert not (res and "The old man walked" in res and "NEPREVEDENO" not in res)
