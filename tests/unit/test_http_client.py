import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network import http_client
import network.model_discovery as _md


def _reset_dead_models():
    """Pomoćnik: čisti dead_models i model list cache između testova."""
    _md.clear_dead_models()
    _md.clear_model_list_cache()


def test_google_pool_uses_only_whitelisted_models(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr(
        "network.model_discovery.get_cached_model_list",
        lambda _provider: [
            "gemini-3-flash",
            "gemini-2.5-flash",       # GA verzija (whitelisted)
            "gemini-3.5-flash",
            "some-random-model",
        ],
    )
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: frozenset())

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    # Modeli koji nisu u statičkom fallback whitelistu ostaju van poola
    assert "gemini-3-flash" not in model_ids
    assert "some-random-model" not in model_ids
    # Whitelistirani modeli su prisutni; statički ai_config redosljed ostaje autoritativan
    assert model_ids[0] == "gemini-3.5-flash"
    assert "gemini-3.5-flash" in model_ids


def test_google_pool_falls_back_when_discovery_empty(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _provider: [])
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: frozenset())
    pool = http_client._get_google_model_pool()

    assert pool == http_client._GOOGLE_MODEL_POOL_FALLBACK


def test_google_pool_excludes_dead_models(monkeypatch):
    """Dead modeli (HTTP 404) moraju biti isključeni iz poola."""
    _reset_dead_models()
    dead_model = "gemini-2.5-flash-lite-preview-06-17"
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _p: [])
    monkeypatch.setattr(
        "network.model_discovery.get_dead_models",
        lambda _p: frozenset({dead_model}),
    )

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    assert dead_model not in model_ids
    # Ostali whitelistirani modeli ostaju
    assert "gemini-3.5-flash" in model_ids


def test_google_pool_preserves_static_order_after_dead_filter(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr(
        "network.model_discovery.get_dead_models",
        lambda _p: frozenset({"gemini-3.5-flash"}),
    )

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    assert model_ids[0] == "gemini-3.1-flash-lite"
    assert model_ids == [
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ]


def test_google_pool_all_dead_returns_full_fallback(monkeypatch):
    """Kad su SVI modeli dead, mora se vratiti puni fallback (sigurnosna mreža)."""
    _reset_dead_models()
    all_dead = frozenset(m["model"] for m in http_client._GOOGLE_MODEL_POOL_FALLBACK)
    monkeypatch.setattr("network.model_discovery.get_cached_model_list", lambda _p: [])
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: all_dead)

    pool = http_client._get_google_model_pool()
    # Ne smijemo vraćati prazan pool (izazvao bi ZeroDivisionError u rotaciji)
    assert len(pool) > 0


def test_mark_model_dead_and_get():
    _reset_dead_models()
    _md.mark_model_dead("GEMINI", "gemini-bad-model")
    dead = _md.get_dead_models("GEMINI")
    assert "gemini-bad-model" in dead


def test_invalidate_cached_model_marks_dead():
    _reset_dead_models()
    # Postavi cache
    _md._set_cached_model_list("GEMINI", ["gemini-2.0-flash", "gemini-2.5-flash-lite-preview-06-17"])

    _md.invalidate_cached_model("GEMINI", "gemini-2.0-flash")

    dead = _md.get_dead_models("GEMINI")
    assert "gemini-2.0-flash" in dead
    # Sljedeći model je promoviran
    cached = _md.get_cached_model("GEMINI")
    assert cached == "gemini-2.5-flash-lite-preview-06-17"


def test_set_cached_model_list_revives_dead_models():
    """Kad API ponovo vrati model koji smo smatrali dead, treba ga oživjeti."""
    _reset_dead_models()
    _md.mark_model_dead("GEMINI", "gemini-2.0-flash")
    assert "gemini-2.0-flash" in _md.get_dead_models("GEMINI")

    # API ponovo vraća model u listi — oživjava ga
    _md._set_cached_model_list("GEMINI", ["gemini-2.0-flash", "gemini-2.5-flash-lite-preview-06-17"])

    assert "gemini-2.0-flash" not in _md.get_dead_models("GEMINI")


def test_build_messages_uses_user_only_for_models_without_system_role():
    msgs = http_client._build_messages("sys", "usr", "gemma-3-27b-it")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert "[INSTRUKCIJE]" in msgs[0]["content"]


def test_build_messages_uses_system_for_supported_models():
    msgs = http_client._build_messages("sys", "usr", "gpt-4o")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_gemini_rotates_model_on_429(monkeypatch):
    """
    Kad ključ dobije 429 na gemini-2.0-flash, mora probati sljedeći
    model (gemini-2.5-flash, gemini-2.0-flash-lite) — ne smije odmah skočiti
    na sljedeći ključ bez pokušaja s drugim modelima.
    """
    import asyncio

    _reset_dead_models()

    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK
    assert len(pool) >= 2, "Test zahtijeva barem 2 modela u pool-u"

    tried_models: list[str] = []

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        # Model je u URL-u za Gemini native: .../models/{model}:generateContent
        model = url.split("/models/")[-1].split(":")[0] if "/models/" in url else ""
        tried_models.append(model)
        if model == pool[0]["model"]:
            return None
        # Drugi model uspijeva — Gemini native format
        return {"candidates": [{"content": {"parts": [{"text": "ODGOVOR"}]}}]}

    monkeypatch.setattr("network.http_client._async_http_post", fake_async_http_post)
    monkeypatch.setattr("network.http_client._get_next_proxy", lambda: None)

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    from api_fleet import FleetManager, KeyState
    _fleet = FleetManager.__new__(FleetManager)
    import threading
    _fleet.lock = threading.Lock()
    _fleet.fleet = {"GEMINI": [KeyState("TEST_KEY_1234", "GEMINI")]}
    _fleet.resolved_models = {"GEMINI": pool[0]["model"]}
    _fleet._rr_index = {}

    class FakeEngine:
        fleet = _fleet

        def log(self, msg, level="info"):
            pass

    engine = FakeEngine()

    result = asyncio.run(
        http_client._call_gemini_with_full_rotation(engine, None, "test", 0.5, 100)
    )
    content, label = result
    assert content == "ODGOVOR", "Trebalo je uspjeti s drugim modelom nakon 429 na prvom"
    assert len(tried_models) >= 2, "Morala su biti isprobana barem 2 modela"
    assert tried_models[0] == pool[0]["model"], "Prvi pokušaj mora biti s primarnim modelom"
    assert tried_models[1] != pool[0]["model"], "Drugi pokušaj mora biti s drugim modelom"


def test_gemini_skips_inactive_key_on_billing(monkeypatch):
    """
    Rotacija mora nastaviti probati OSTALE modele s istim ključem jer svaki
    Gemini model ima NEZAVISNE RPD kvote.
    Svi modeli u pool-u trebaju biti isprobani (tried_models == len(pool)).
    """
    import asyncio

    _reset_dead_models()

    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK

    tried_models: list[str] = []

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        model = payload.get("model", "")
        tried_models.append(model)
        # Svi modeli vraćaju None — simulira billing/kvotu
        return None

    monkeypatch.setattr("network.http_client._async_http_post", fake_async_http_post)
    monkeypatch.setattr("network.http_client._get_next_proxy", lambda: None)

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    from api_fleet import FleetManager, KeyState
    _fleet = FleetManager.__new__(FleetManager)
    import threading
    _fleet.lock = threading.Lock()
    _fleet.fleet = {"GEMINI": [KeyState("BILLING_KEY_5678", "GEMINI")]}
    _fleet.resolved_models = {"GEMINI": pool[0]["model"]}
    _fleet._rr_index = {}

    class FakeEngine:
        fleet = _fleet

        def log(self, msg, level="info"):
            pass

    engine = FakeEngine()

    result = asyncio.run(
        http_client._call_gemini_with_full_rotation(engine, None, "test", 0.5, 100)
    )
    content, label = result
    assert content is None, "Billing-iscrpljeni ključ ne smije uspjeti"
    # BUG FIX: moraju biti isprobani SVI modeli — svaki ima nezavisnu kvotu.
    # Staro ponašanje (samo 1 model) je bilo pogrešno jer je spriječavalo rotaciju
    # na gemini-2.5-flash, gemini-2.0-flash-lite i gemma-4 kad je 2.0-flash iscrpljen.
    assert len(tried_models) == len(pool), (
        f"Rotacija mora isprobati sve {len(pool)} modela, pokušano: {tried_models}"
    )


def test_gemini_fresh_snapshot_picks_up_new_key(monkeypatch):
    """
    Bug 2 fix: Ako su SVI ključevi u početnom snapshotu iscrpljeni, sistem treba
    provjeriti flotu još jednom (svježi snapshot) da uhvati ključeve koji su
    dodani za vrijeme rotacije ili se probudili iz cooldowna.
    """
    import asyncio
    import threading
    from api_fleet import FleetManager, KeyState

    _reset_dead_models()

    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK

    call_count = [0]

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        call_count[0] += 1
        if key == "OLD_KEY_0001":
            # Stari ključ — svi pozivi vraćaju None
            return None
        # Novi ključ koji je "dodan za vrijeme rotacije" — Gemini native format
        return {"candidates": [{"content": {"parts": [{"text": "NOVI_KLJUČ_ODGOVOR"}]}}]}

    monkeypatch.setattr("network.http_client._async_http_post", fake_async_http_post)
    monkeypatch.setattr("network.http_client._get_next_proxy", lambda: None)
    monkeypatch.setattr("asyncio.sleep", lambda _s: asyncio.coroutine(lambda: None)())

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    _fleet = FleetManager.__new__(FleetManager)
    _fleet.lock = threading.Lock()
    # Fleet ima 2 ključa: OLD_KEY koji uvijek failuje + NEW_KEY koji uspijeva.
    # OLD_KEY je posortiran ispred NEW_KEY po success_rate (oba novi = 1.0, round-robin).
    old_ks = KeyState("OLD_KEY_0001", "GEMINI")
    new_ks = KeyState("NEW_KEY_9999", "GEMINI")
    # OLD_KEY ima lošiji success_rate da bude iza NEW_KEY ili svejedno — oba će biti isprobana
    old_ks.calls_failed = 10
    _fleet.fleet = {"GEMINI": [old_ks, new_ks]}
    _fleet.resolved_models = {"GEMINI": pool[0]["model"]}
    _fleet._rr_index = {}

    class FakeEngine:
        fleet = _fleet

        def log(self, msg, level="info"):
            pass

    engine = FakeEngine()

    result = asyncio.run(
        http_client._call_gemini_with_full_rotation(engine, None, "test", 0.5, 100)
    )
    content, label = result
    assert content == "NOVI_KLJUČ_ODGOVOR", (
        "Svježi snapshot treba uhvatiti novi ključ i uspjeti"
    )


def test_gemini_resets_key_model_cache_after_full_exhaustion(monkeypatch):
    import asyncio
    import threading
    from api_fleet import FleetManager, KeyState

    _reset_dead_models()
    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK
    key = "RESET_KEY_1234"

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        return None

    monkeypatch.setattr("network.http_client._async_http_post", fake_async_http_post)

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    fleet = FleetManager.__new__(FleetManager)
    fleet.lock = threading.Lock()
    fleet.fleet = {"GEMINI": [KeyState(key, "GEMINI")]}
    fleet.resolved_models = {"GEMINI": pool[0]["model"]}
    fleet._rr_index = {}

    class FakeEngine:
        def __init__(self, fleet_obj):
            self.fleet = fleet_obj

        def log(self, msg, level="info"):
            pass

    http_client._key_model_cache[key] = len(pool) - 1
    asyncio.run(http_client._call_gemini_with_full_rotation(FakeEngine(fleet), None, "test", 0.5, 100))

    assert http_client._get_model_for_key(key, pool) == pool[0]["model"]
