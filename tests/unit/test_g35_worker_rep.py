"""G35/G36: rep workera je iskljucen po defaultu; poglavlje se i dalje prevodi i prepisuje."""
import asyncio
import inspect

import pytest

from tests.unit.test_l58_smoke import _lazni, engine  # noqa: F401
from tests.unit.test_l58_workers import HR, _bez_cekanja, _bez_mreze, _pripremi  # noqa: F401


def test_rep_po_defaultu_iskljucen(monkeypatch):
    import processing.workers as w

    monkeypatch.delenv("BOOKLYFI_WORKER_REP", raising=False)
    assert w._worker_rep_ukljucen() is False
    monkeypatch.setenv("BOOKLYFI_WORKER_REP", "1")
    assert w._worker_rep_ukljucen() is True


def test_bez_repa_nema_scorera_ni_retrya(engine, monkeypatch):  # noqa: F811
    import core.quality as q
    import processing.workers as w

    monkeypatch.delenv("BOOKLYFI_WORKER_REP", raising=False)

    def _zabrani(*a, **k):
        raise AssertionError("rep workera pozvan iako je iskljucen")

    for modul in (w, q):
        for ime in ("_retry_s_feedbackom", "_qa_ai_ocjena"):
            if hasattr(modul, ime):
                monkeypatch.setattr(modul, ime, _zabrani)
    f = _pripremi(engine)
    _lazni(engine, lambda u, p: (HR, "LAZNI"))
    asyncio.run(engine.process_single_file_worker(f))
    out = f.read_text("utf-8")
    assert "Starac" in out and "The old man" not in out


def test_kratki_izlaz_uvjet_je_relativan():
    import processing.workers as w

    src = inspect.getsource(w.process_single_file_worker)
    assert "len(res.strip()) < 50 and len(chunks[i].strip()) >= 200" in src
