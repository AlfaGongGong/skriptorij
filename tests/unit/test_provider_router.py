import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network.provider_router import _resolve_model_generation_params


def test_resolve_model_generation_params_applies_exact_model_override():
    temp, max_tokens = _resolve_model_generation_params(
        "PREVODILAC",
        "gemini-2.0-flash",
        0.5,
        2800,
    )
    assert round(temp, 3) == round(0.5 * 0.88, 3)
    assert max_tokens == 2200


def test_resolve_model_generation_params_applies_family_fallback():
    temp, max_tokens = _resolve_model_generation_params(
        "LEKTOR",
        "some-unknown-gemini-model",
        0.45,
        2800,
    )
    assert round(temp, 3) == round(0.45 * 0.90, 3)
    assert max_tokens == 2200
