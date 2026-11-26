import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.ai_config import GOOGLE_MODEL_POOL, MORFO_VALIDATOR_MODEL, PROVIDER_PRIORITY


def test_google_model_pool_uses_current_rpd_limits():
    by_model = {entry["model"]: entry for entry in GOOGLE_MODEL_POOL}

    # Pool sadrzi samo aktivne modele (3.5 i 3.1 flash-lite).
    # 2.5-flash i 2.5-flash-lite su uklonjeni iz pool-a.
    assert by_model["gemini-3.5-flash-lite"]["rpd"] == 500
    assert by_model["gemini-3.1-flash-lite"]["rpd"] == 500


def test_samo_aktivni_provideri_u_prioritetima():
    from config.ai_config import AKTIVNI_PROVIDERI

    for role, lista in PROVIDER_PRIORITY.items():
        assert lista, role
        assert set(lista) <= set(AKTIVNI_PROVIDERI), role
        assert "GEMMA" not in lista


def test_morfo_validator_uses_high_quota_google_model():
    assert MORFO_VALIDATOR_MODEL == "gemini-3.1-flash-lite"
