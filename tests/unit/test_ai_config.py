import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.ai_config import GOOGLE_MODEL_POOL, MORFO_VALIDATOR_MODEL, PROVIDER_PRIORITY


def test_google_model_pool_uses_current_rpd_limits():
    by_model = {entry["model"]: entry for entry in GOOGLE_MODEL_POOL}

    assert by_model["gemini-3.5-flash"]["rpd"] == 20
    assert by_model["gemini-3.1-flash-lite"]["rpd"] == 500
    assert by_model["gemini-2.5-flash-lite"]["rpd"] == 20
    assert by_model["gemini-2.5-flash"]["rpd"] == 20


def test_gemma_is_present_in_secondary_provider_priorities():
    for role in ("GUARDIAN", "POLISH", "SCORER", "GLOSAR_UPDATE"):
        assert "GEMMA" in PROVIDER_PRIORITY[role]


def test_morfo_validator_uses_high_quota_google_model():
    assert MORFO_VALIDATOR_MODEL == "gemini-3.1-flash-lite"
