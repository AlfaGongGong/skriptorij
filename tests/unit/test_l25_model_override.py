from config.model_roles import pick_model_for_role

M = [
    {"model": "gemini-3.5-flash-lite", "rpd": 500, "latency_s": 12.0},
    {"model": "gemini-3.5-flash", "rpd": 20, "latency_s": 8.0},
]


def test_bez_env_ostaje_lite(monkeypatch):
    monkeypatch.delenv("BOOKLYFI_MODEL_PREVODILAC", raising=False)
    assert pick_model_for_role("PREVODILAC", M) == "gemini-3.5-flash-lite"


def test_override_bira_flash(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_MODEL_PREVODILAC", "gemini-3.5-flash")
    assert pick_model_for_role("PREVODILAC", M) == "gemini-3.5-flash"


def test_override_nepostojeci_model_ignoriran(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_MODEL_PREVODILAC", "nema-takvog")
    assert pick_model_for_role("PREVODILAC", M) == "gemini-3.5-flash-lite"


def test_druge_uloge_netaknute(monkeypatch):
    monkeypatch.setenv("BOOKLYFI_MODEL_PREVODILAC", "gemini-3.5-flash")
    assert pick_model_for_role("LEKTOR", M) == "gemini-3.5-flash-lite"
