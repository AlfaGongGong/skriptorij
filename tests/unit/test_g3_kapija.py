"""G3: strukturna kapija (core/strukturna_kapija.py) + ugradnja u process_chunk_with_ai."""
import asyncio
import zipfile
from pathlib import Path

import pytest

from core.strukturna_kapija import provjeri

EN = (
    "<p>The old man walked slowly down the road, and the wind was cold against his face in 1843.</p>"
    "<p>\u201cI have not seen Rhodri for many years,\u201d said Katherine to Gareth.</p>"
    "<p>\u201cYou will never find him,\u201d answered Gareth. \u201cNobody has, and I did not try.\u201d</p>"
    "<p>They walked on until the night came, and Katherine did not speak again.</p>"
)
HR = (
    "<p>Starac je polako hodao cestom, a vjetar mu je hladno puhao u lice 1843. godine.</p>"
    "<p>\u2014 Nisam vidio Rhodrija godinama \u2014 rekla je Katherine Garethu.</p>"
    "<p>\u2014 Nikad ga nećeš naći \u2014 odgovorio je Gareth. \u2014 Nitko nije, a ni ja nisam pokušao.</p>"
    "<p>Hodali su dok nije pala noć, a Katherine nije više progovorila.</p>"
)


def test_dobar_prijevod_prolazi():
    assert provjeri(EN, HR) == []


def test_izgubljen_odlomak():
    hr = HR.replace("<p>Hodali su dok nije pala noć, a Katherine nije više progovorila.</p>", "")
    assert any(r.startswith("odlomci") for r in provjeri(EN, hr))


def test_promijenjen_broj():
    r = provjeri(EN, HR.replace("1843", "1834"))
    assert any(x.startswith("brojevi") for x in r)


def test_format_broja_ne_smeta():
    assert provjeri("<p>It cost 1,000 coins.</p><p>Ok then.</p>", "<p>Stajalo je 1.000 novčića.</p><p>U redu.</p>") == []


def test_nestala_imena():
    hr = HR.replace("Katherine", "ona").replace("Gareth", "on").replace("Rhodrija", "njega")
    assert any(x.startswith("imena") for x in provjeri(EN, hr))


def test_glosar_prihvaca_hrvatski_oblik():
    hr = HR.replace("Rhodrija", "Rodrija")
    gl = "- Rhodri -> Rodri [lik]"
    assert not any(x.startswith("imena") for x in provjeri(EN, hr, gl))


def test_replike_nestale():
    hr = HR.replace("\u2014 ", "")
    assert any(x.startswith("replike") for x in provjeri(EN, hr))


def test_negacije_nestale():
    en = "<p>He did not go. Never. Nobody did. Nothing happened, nor did he try.</p><p>Fine.</p>"
    hr = "<p>Otišao je. Odlazio je. Svi su išli. Dogodilo se sve, a on je probao.</p><p>Dobro.</p>"
    assert any(x.startswith("negacije") for x in provjeri(en, hr))


def test_prazno_prolazi():
    assert provjeri("", "<p>x</p>") == [] and provjeri("<p>x</p>", "") == []


# --- integracija kroz pipeline (lazni provider, kao L58) ---
class _LazniFleet:
    fleet = {}

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def engine(tmp_path, monkeypatch):
    import core.engine as eng
    import network.model_discovery as md

    monkeypatch.setattr(eng, "CHECKPOINT_BASE_DIR", tmp_path / "cp")
    monkeypatch.setattr(eng, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(eng, "FleetManager", _LazniFleet)
    monkeypatch.setattr(md, "start_background_discovery", lambda *a, **k: None)
    epub = tmp_path / "Mala_Knjiga.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    e = eng.SkriptorijAllInOne(str(epub), "test", {"quality_scores": {}}, {"stop": False})
    e.knjiga_mode = "PREVOD"
    e.poziva = []
    return e


def _lazni(e, odgovor):
    async def _call(prompt, chunk_idx, *a, uloga="", **k):
        e.poziva.append(uloga)
        return odgovor, "LAZNI"

    e._call_ai_engine = _call


def test_pipeline_odbija_dva_puta_pa_prihvaca(engine):
    hr_los = HR.replace("<p>Hodali su dok nije pala noć, a Katherine nije više progovorila.</p>", "")
    _lazni(engine, hr_los)
    rez = [asyncio.run(engine.process_chunk_with_ai(EN, "", "", 0, "chapter001.html")) for _ in range(3)]
    assert rez[0][0] is None and rez[0][1] == "STRUKT"
    assert rez[1][0] is None and rez[1][1] == "STRUKT"
    assert rez[2][0] is not None  # fail-open: blok ne smije nestati


def test_pipeline_dobar_prijevod_odmah_upisan(engine):
    _lazni(engine, HR)
    res, tag = asyncio.run(engine.process_chunk_with_ai(EN, "", "", 0, "chapter001.html"))
    assert res is not None and tag != "STRUKT"
    assert list(Path(engine.checkpoint_dir).glob("*.chk"))
