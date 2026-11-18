"""L58 DIO 2: smoke test process_single_file_worker (workers.py) s lazim providerom.

Mini poglavlje (3 odlomka) kroz chunkanje, paralelnu obradu, .chk i prepis HTML-a.
Bez mreze; vidi test_l58_smoke.py za engine fixture.
"""
import asyncio
import re
from pathlib import Path

import pytest

from tests.unit.test_l58_smoke import _lazni, engine  # noqa: F401

POGLAVLJE = (
    "<html><head><title>Chapter</title></head><body>"
    "<h1>One</h1>"
    "<p>The old man walked slowly down the road, and the wind was cold against his face. "
    "He had not seen his brother for many years, and he did not know what he would say.</p>"
    "<p>The house stood at the end of the lane, and a light was burning in the window. "
    "He stopped at the gate and listened to the silence of the evening.</p>"
    "</body></html>"
)
HR = (
    "<h1>Prvo</h1><p>Starac je polako hodao cestom, a vjetar mu je hladno puhao u lice. "
    "Nije vidio brata godinama i nije znao što će mu reći.</p>"
    "<p>Kuća je stajala na kraju staze, a u prozoru je gorjelo svjetlo. "
    "Zastao je na vratima i slušao tišinu večeri.</p>"
)


@pytest.fixture(autouse=True)
def _bez_cekanja(monkeypatch):
    """Ponovni pokusaji bloka (P2.9) cekaju 20 s; u testu 0."""
    import processing.parallel as par

    monkeypatch.setattr(par, "_RETRY_PAUZA", 0)
    _orig_init = par.AdaptiveParallelism.__init__

    def _init(self, engine):
        _orig_init(self, engine)
        self._human_delay = (0.0, 0.0)

    monkeypatch.setattr(par.AdaptiveParallelism, "__init__", _init)


@pytest.fixture(autouse=True)
def _bez_mreze(monkeypatch):
    """Test ne smije otvoriti pravu mreznu vezu."""
    import socket

    pozivi = []

    def _zabrani(self, *a, **k):
        pozivi.append(a)
        raise OSError("L58: mreza zabranjena u testu")

    monkeypatch.setattr(socket.socket, "connect", _zabrani)
    # classla (DinamickiDetektor) u testu iskljucena: nema skidanja modela
    import core.kalkovi.dinamicki_detektor as dd

    monkeypatch.setattr(dd, "CLASSLA_DOSTUPAN", False)
    yield
    assert not pozivi, f"test je pokusao mrezu: {pozivi}"


def _pripremi(e):
    e.fleet.get_total_active_keys = lambda: 2
    e.fleet.keys = lambda: []
    e.buildlive_epub = lambda *a, **k: None
    tekst = Path(e.work_dir) / "text"
    tekst.mkdir(parents=True, exist_ok=True)
    f = tekst / "chapter001.html"
    f.write_text(POGLAVLJE, encoding="utf-8")
    return f


def test_poglavlje_se_prevodi_i_prepisuje(engine):  # noqa: F811
    f = _pripremi(engine)
    _lazni(engine, lambda u, p: (HR, "LAZNI"))
    asyncio.run(engine.process_single_file_worker(f))
    out = f.read_text("utf-8")
    assert "Starac" in out
    assert "The old man" not in out
    assert "NEPREVEDENO" not in out
    assert "chunk_sha" not in out
    assert list(Path(engine.checkpoint_dir).glob("chapter001.html_blok_*.chk"))
    # izvor EN je sacuvan za ponovni prolaz (P2.20)
    assert list((Path(engine.checkpoint_dir) / "izvor_en").glob("*.en"))


def test_provider_pada_upisuje_marker_i_poglavlje_ostaje_citljivo(engine):  # noqa: F811
    f = _pripremi(engine)
    _lazni(engine, lambda u, p: (None, ""))
    asyncio.run(engine.process_single_file_worker(f))
    out = f.read_text("utf-8")
    assert re.search(r"NEPREVEDENO: blok \d+", out)
    assert "<body" in out


def test_kvota_stop_ne_prepisuje_poglavlje(engine, monkeypatch):  # noqa: F811
    f = _pripremi(engine)
    prije = f.read_text("utf-8")
    import network.quota_tracker as qt

    monkeypatch.setattr(
        qt.quota_tracker, "dnevna_kvota_iscrpljena", lambda *a, **k: (True, 7200.0)
    )
    _lazni(engine, lambda u, p: (None, "ALL_FAILED"))
    asyncio.run(engine.process_single_file_worker(f))
    assert getattr(engine, "kvota_stop", False) is True
    assert f.read_text("utf-8") == prije, "kvota_stop: poglavlje se ne smije prepisati"
    assert engine.shared_controls.get("stop") is True
    assert not list(Path(engine.checkpoint_dir).glob("chapter001.html_blok_*.chk")), (
        "kvota_stop ne smije upisati marker .chk"
    )
