import asyncio
import pytest


class _L:
    def __init__(self):
        self.w = []
    def warning(self, *a, **k):
        self.w.append(a)
    def __getattr__(self, n):
        return lambda *a, **k: None


def test_izuzetak_se_logira_i_propagira(monkeypatch):
    from network import provider_router as R
    L = _L()
    async def _fake(*a, **k):
        raise TimeoutError("test 60s")
    monkeypatch.setattr(R, "logger", L)
    monkeypatch.setattr(R, "_call_ai_engine_impl", _fake)
    monkeypatch.setattr(R, "_g16_zapisi", lambda *a, **k: None)
    with pytest.raises(TimeoutError):
        asyncio.run(R._call_ai_engine(None, 'p', 0, uloga='VERIFIER'))
    assert any("VERIFIER" in str(a) and "TimeoutError" in str(a) for a in L.w)
