"""Testovi ne smiju koristiti stvarne knjige iz checkpoint mape uredjaja (podudaranje imena _skr_*)."""
import pytest


@pytest.fixture(autouse=True)
def _prazna_checkpoint_mapa(tmp_path_factory, monkeypatch):
    import config.settings as cfg

    monkeypatch.setattr(cfg, "CHECKPOINT_BASE_DIR", tmp_path_factory.mktemp("cp_prazno"))
