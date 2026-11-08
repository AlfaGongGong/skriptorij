import pytest

P = pytest.importorskip("api.routes.processing", reason="processing.py se ne moze uvesti")


@pytest.mark.parametrize("cf,ocekivano", [
    ("---", ""), ("", ""), ("—", ""),
    ("Delacroix.epub", "Delacroix"),
    ("PREVEDENO_Delacroix_STYLED.epub", "Delacroix"),
])
def test_p26_knjiga(monkeypatch, tmp_path, cf, ocekivano):
    monkeypatch.setattr(P, "SHARED_STATS", {"current_file": cf})
    monkeypatch.setattr(P, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(P, "CHECKPOINT_BASE_DIR", tmp_path / "prazno")
    assert P._p26_knjiga() == ocekivano
