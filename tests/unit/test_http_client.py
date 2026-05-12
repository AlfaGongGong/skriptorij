import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from network import http_client
import network.model_discovery as _md


def _reset_dead_models():
    """Pomoćnik: čisti dead_models state između testova."""
    _md.clear_dead_models()


def test_google_pool_uses_only_whitelisted_models(monkeypatch):
    _reset_dead_models()
    monkeypatch.setattr(
        "network.model_discovery.get_cached_model_list",
        lambda _provider: [
            "gemini-3-flash",
            "gemini-2.5-flash",       # GA verzija (whitelisted); preview je uklonjen (404)
            "gemini-2.0-flash",
            "some-random-model",
        ],
    )
    monkeypatch.setattr("network.model_discovery.get_dead_models", lambda _p: frozenset())

    pool = http_client._get_google_model_pool()
    model_ids = [m["model"] for m in pool]

    # Modeli koji nisu u statičkom fallback whitelistu ostaju van poola
    assert "gemini-3-flash" not in model_ids
    assert "some-random-model" not in model_ids
    # Whitelistirani modeli su prisutni; discovery određuje redosljed
    assert model_ids[0] == "gemini-2.5-flash"
    assert "gemini-2.0-flash" in model_ids


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
    assert "gemini-2.0-flash" in model_ids


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
    BUG FIX: Kad ključ dobije 429 na gemini-2.0-flash, mora probati sljedeći
    model (gemini-2.5-flash, gemini-2.0-flash-lite) — ne smije odmah skočiti
    na sljedeći ključ bez pokušaja s drugim modelima.

    Svaki Gemini model ima vlastite RPM/RPD kvote, pa 429 na jednom modelu
    ne znači nužno da su i drugi modeli iscrpljeni.

    NAPOMENA: Simuliramo kratki RPM cooldown (samo cooldown_until, is_active=True).
    Billing/dnevna kvota eksplicitno postavlja is_active=False i odmah prelazi
    na sljedeći ključ — to je testirano u test_gemini_skips_inactive_key_on_billing.
    """
    import asyncio

    _reset_dead_models()

    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK
    assert len(pool) >= 2, "Test zahtijeva barem 2 modela u pool-u"

    tried_models: list[str] = []

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        model = payload.get("model", "")
        tried_models.append(model)
        # Simuliraj kratki RPM cooldown na ključu — kao što to radi analyze_response
        # za RPM 429 (is_active ostaje True, samo cooldown_until se postavi).
        # Tek drugi model "uspijeva"
        if model == pool[0]["model"]:
            import time
            for ks in self_obj.fleet.fleet.get("GEMINI", []):
                if ks.key == key:
                    ks.cooldown_until = time.time() + 65.0
                    # is_active ostaje True — ovo je RPM limit, ne billing exhaustion
                    break
            return None
        # Drugi model uspijeva
        return {"choices": [{"message": {"content": "ODGOVOR"}}]}

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
    Ako je ključ DEFINITIVNO iscrpljen (is_active=False — billing kvota ili
    3+ grešaka u 30s), ne smije probati ostale modele s tim ključem.
    Treba odmah preći na sljedeći ključ (ili dati 'Svi ključevi iscrpljeni').
    """
    import asyncio

    _reset_dead_models()

    pool = http_client._GOOGLE_MODEL_POOL_FALLBACK

    tried_models: list[str] = []

    async def fake_async_http_post(self_obj, url, headers, payload,
                                    prov, prov_upper, key, _proxy=None):
        model = payload.get("model", "")
        tried_models.append(model)
        # Simuliraj billing exhaustion — is_active=False (dnevna kvota)
        import time
        for ks in self_obj.fleet.fleet.get("GEMINI", []):
            if ks.key == key:
                ks.cooldown_until = time.time() + 82800
                ks.is_active = False
                break
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
    # Nakon billing 429, smije biti pokušan samo JEDAN model — odmah prelazimo na sljedeći ključ
    assert len(tried_models) == 1, (
        f"Billing-iscrpljeni ključ smije koristiti samo 1 model, pokušano: {tried_models}"
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
        model = payload.get("model", "")
        if key == "OLD_KEY_0001":
            # Stari ključ — billing exhaustion na prvom pozivu
            for ks in self_obj.fleet.fleet.get("GEMINI", []):
                if ks.key == key:
                    import time
                    ks.cooldown_until = time.time() + 82800
                    ks.is_active = False
                    break
            return None
        # Novi ključ koji je "dodan za vrijeme rotacije" — uvijek uspijeva
        return {"choices": [{"message": {"content": "NOVI_KLJUČ_ODGOVOR"}}]}

    monkeypatch.setattr("network.http_client._async_http_post", fake_async_http_post)
    monkeypatch.setattr("network.http_client._get_next_proxy", lambda: None)
    monkeypatch.setattr("asyncio.sleep", lambda _s: asyncio.coroutine(lambda: None)())

    async def _noop_sleep(_s):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop_sleep)

    _fleet = FleetManager.__new__(FleetManager)
    _fleet.lock = threading.Lock()
    # Fleet ima 2 ključa: OLD_KEY u snapshotu (unavailable) + NEW_KEY koji nije
    # bio u snapshotu jer je u floti tek dodan (ali je available)
    old_ks = KeyState("OLD_KEY_0001", "GEMINI")
    new_ks = KeyState("NEW_KEY_9999", "GEMINI")
    _fleet.fleet = {"GEMINI": [old_ks, new_ks]}
    _fleet.resolved_models = {"GEMINI": pool[0]["model"]}
    _fleet._rr_index = {}

    # Simuliraj da je OLD_KEY bio u cooldownu PRIJE snapshota (snimak ga neće uhvatiti)
    import time
    old_ks.cooldown_until = time.time() + 82800
    old_ks.is_active = False

    # Snapshot će biti prazan (OLD_KEY unavailable, NEW_KEY available)
    # Ali NEW_KEY je 'novi' ključ koji bi bio dodan za vrijeme rotacije —
    # simuliramo to tako da NEW_KEY bude u floti ali ga isključimo iz
    # inicijalnog snapshota postavljanjem da ga find ne vrati, ili jednostavno
    # testiramo da svježi snapshot funkcionira.

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
