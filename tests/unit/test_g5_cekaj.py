"""G5: automatsko cekanje reseta dnevne kvote umjesto zaustavljanja."""
import asyncio
import inspect
import time
from types import SimpleNamespace

from processing import workers as W


def _eng(do, stop=False):
    return SimpleNamespace(
        log=lambda *a, **k: None,
        kvota_stop=True,
        kvota_stop_do=do,
        shared_controls={"stop": stop},
        shared_stats={},
    )


def test_ceka_i_nastavlja():
    e = _eng(time.time() + 0.2)
    assert asyncio.run(W._cekaj_reset_kvote(e, "a.html")) is True
    assert e.kvota_stop is False


def test_korisnicki_stop_prekida_cekanje():
    e = _eng(time.time() + 600, stop=True)
    assert asyncio.run(W._cekaj_reset_kvote(e, "a.html")) is False
    assert e.kvota_stop is True


def test_iskljuceno_envom(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_CEKAJ", "0")
    e = _eng(time.time() + 0.1)
    assert asyncio.run(W._cekaj_reset_kvote(e, "a.html")) is False


def test_najvise_tri_pokusaja():
    e = _eng(time.time() + 0.05)
    r = []
    for _ in range(4):
        e.kvota_stop = True
        e.kvota_stop_do = time.time() + 0.05
        r.append(asyncio.run(W._cekaj_reset_kvote(e, "a.html")))
    assert r == [True, True, True, False]


def test_worker_zove_cekaj():
    src = inspect.getsource(W.process_single_file_worker)
    assert "_cekaj_reset_kvote(self, file_name)" in src
