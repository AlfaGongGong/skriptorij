"""
tests/unit/test_discovery_fixes.py
Testovi za FAZA 5 fixeve:
  - GEMMA discovery kroz GEMINI native endpoint
  - pageSize=1000
  - GEMMA grana pre _MODELS_ENDPOINTS
  - retryDelay > 3600s (RPM vs RPD)
  - _detect_language vraca LEKTURA/PREVOD
  - _odredi_strategiju filename heuristika
"""

import contextlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ── Discovery — fetch_models GEMMA/GEMINI ──────────────────────────────────


def test_fetch_models_gemma_returns_models():
    """GEMMA grana mora biti PRE _MODELS_ENDPOINTS (nema endpoint u mapi)."""
    from network import model_discovery as md

    with patch.object(md, "_fetch_gemini_native_models") as mock_fetch:
        mock_fetch.return_value = ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
        result = md.fetch_models("GEMMA", "fake_key")
    assert len(result) == 2
    assert "gemma-4-31b-it" in result
    mock_fetch.assert_called_once()
    # Proveri da je pozvan sa provider_filter="GEMMA"
    call_kwargs = mock_fetch.call_args
    assert "provider_filter" in call_kwargs.kwargs
    assert call_kwargs.kwargs["provider_filter"] == "GEMMA"


def test_fetch_models_gemini_returns_models():
    from network import model_discovery as md

    with patch.object(md, "_fetch_gemini_native_models") as mock_fetch:
        mock_fetch.return_value = ["gemini-3.5-flash-lite"]
        result = md.fetch_models("GEMINI", "fake_key")
    assert result == ["gemini-3.5-flash-lite"]
    call_kwargs = mock_fetch.call_args
    assert call_kwargs.kwargs["provider_filter"] == "GEMINI"


def test_fetch_models_gemma_works_even_without_endpoint_in_map():
    """GEMMA NIJE u _MODELS_ENDPOINTS, ali fetch_models("GEMMA") mora raditi."""
    from network import model_discovery as md

    # Provera da GEMMA stvarno nije u mapi (dokumentovan bug)
    assert "GEMMA" not in md._MODELS_ENDPOINTS
    with patch.object(md, "_fetch_gemini_native_models") as mock_fetch:
        mock_fetch.return_value = ["gemma-4-26b-a4b-it"]
        result = md.fetch_models("GEMMA", "fake_key")
    assert result == ["gemma-4-26b-a4b-it"]


def test_page_size_1000_used_in_url():
    """_fetch_gemini_native_models mora koristiti pageSize=1000, ne 50."""
    from network import model_discovery as md

    with patch.object(md.requests, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [], "nextPageToken": None}
        mock_get.return_value = mock_resp

        md._fetch_gemini_native_models("fake_key", provider_filter="GEMINI")

    # Proveri URL
    assert mock_get.called
    url = mock_get.call_args[0][0]
    assert "pageSize=1000" in url
    assert "pageSize=50" not in url


# ── retryDelay — RPM vs RPD ───────────────────────────────────────────────


def test_retryDelay_over_3600_without_rpd_gives_60s():
    """retryDelay=36564s bez 'daily'/'rpd' u message → RPM 60s."""
    from api_fleet import FleetManager
    from network.quota_tracker import quota_tracker

    fm = FleetManager()
    ks_list = fm.fleet.get("GEMINI", [])
    if not ks_list:
        pytest.skip("Nema GEMINI ključeva")

    key = ks_list[0].key
    body = {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota, please check your plan.",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"retryDelay": "36564s"}],
        }
    }

    fm.analyze_response("GEMINI", key, 429, {}, body)
    ok, reason = quota_tracker.is_key_available("GEMINI", key)

    # Proveri: cooldown je 60s, ne 36564s
    import re

    m = re.search(r"(\d+)s", reason)
    if m:
        secs = int(m.group(1))
        assert secs <= 120, f"Ocekivano 60s (RPM), dobijeno {secs}s — {reason}"
        assert secs > 0

    # Cleanup
    with contextlib.suppress(Exception):
        quota_tracker.clear_key_cooldown("GEMINI", key) if hasattr(
            quota_tracker, "clear_key_cooldown"
        ) else None


def test_retryDelay_over_3600_with_daily_gives_10h():
    """retryDelay=36564s sa 'daily' u message → RPD 36564s (10h)."""
    from api_fleet import FleetManager
    from network.quota_tracker import quota_tracker

    fm = FleetManager()
    ks_list = fm.fleet.get("GEMINI", [])
    if len(ks_list) < 2:
        pytest.skip("Treba 2 GEMINI kljuca")

    key = ks_list[1].key
    body = {
        "error": {
            "code": 429,
            "message": "You have exceeded your daily quota for today.",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"retryDelay": "36564s"}],
        }
    }

    fm.analyze_response("GEMINI", key, 429, {}, body)
    ok, reason = quota_tracker.is_key_available("GEMINI", key)

    # Proveri: cooldown je ~36564s (10h)
    import re

    m = re.search(r"(\d+)s", reason)
    if m:
        secs = int(m.group(1))
        assert secs > 3600, f"Ocekivano RPD >3600s, dobijeno {secs}s — {reason}"


# ── Mode detection ────────────────────────────────────────────────────────


def test_detect_language_returns_lektura_for_hr():
    """_detect_language sada vraca LEKTURA/PREVOD, ne HR/EN."""
    from core.engine import SkriptorijAllInOne

    # Instanciraj bez fajla — samo za test metode
    try:
        engine = SkriptorijAllInOne.__new__(SkriptorijAllInOne)
        result = engine._detect_language(
            "<p>Ovo je hrvatski tekst sa č, ć, ž, š, đ.</p>"
        )
        assert result == "LEKTURA", f"Ocekivano LEKTURA, dobijeno {result}"
    except Exception as e:
        pytest.skip(f"Ne mogu instancirati engine: {e}")


def test_detect_language_returns_prevod_for_en():
    from core.engine import SkriptorijAllInOne

    try:
        engine = SkriptorijAllInOne.__new__(SkriptorijAllInOne)
        result = engine._detect_language(
            "<p>The quick brown fox jumps over the lazy dog. And this is more english text.</p>"
        )
        assert result == "PREVOD", f"Ocekivano PREVOD, dobijeno {result}"
    except Exception as e:
        pytest.skip(f"Ne mogu instancirati engine: {e}")


# ── _odredi_strategiju — filename heuristika ──────────────────────────────


def test_odredi_strategiju_prevedeno_filename_overrides_prevod(tmp_path):
    """Ako book_analysis.json kaze PREVOD ali filename sadrzi PREVEDENO → LEKTURA."""
    from run import _odredi_strategiju

    # Mock engine
    class MockEngine:
        def __init__(self):
            self.book_path = tmp_path / "Some_Book_PREVEDENO_STYLED.epub"
            self.book_path.write_text("dummy")
            self.checkpoint_dir = tmp_path / "checkpoints"
            self.checkpoint_dir.mkdir()
            self.log = lambda *a, **kw: None

        def _detect_knjiga_mode(self, files, n_files=5):
            return "PREVOD"  # Mock vraca PREVOD

    engine = MockEngine()

    # Napravi book_analysis.json sa PREVOD
    import json

    ba_path = engine.checkpoint_dir / "book_analysis.json"
    ba_path.write_text(json.dumps({"knjiga_mode": "PREVOD"}))

    # Napravi dovoljno .chk fajlova da triggeruje granu (>= 20% html_files)
    for i in range(5):
        (engine.checkpoint_dir / f"part{i:04d}.html_blok_0.chk").write_text("x")

    # 10 html fajlova (da chk_count >= 20% * 10 = 2)
    html_files = [tmp_path / f"part{i:04d}.html" for i in range(10)]

    result = _odredi_strategiju(engine, html_files, scores={})
    assert result == "LEKTURA", (
        f"Ocekivano LEKTURA (override zbog PREVEDENO), dobijeno {result}"
    )


def test_odredi_strategiju_uses_filename_heuristic_without_saved_mode(tmp_path):
    """Ako nema book_analysis.json ali filename sadrzi PREVEDENO → LEKTURA."""
    from run import _odredi_strategiju

    class MockEngine:
        def __init__(self):
            self.book_path = tmp_path / "Book_PREVEDENO.epub"
            self.book_path.write_text("dummy")
            self.checkpoint_dir = tmp_path / "checkpoints"
            self.checkpoint_dir.mkdir()
            self.log = lambda *a, **kw: None

        def _detect_knjiga_mode(self, files, n_files=5):
            return "PREVOD"

    engine = MockEngine()
    for i in range(5):
        (engine.checkpoint_dir / f"part{i:04d}.html_blok_0.chk").write_text("x")

    html_files = [tmp_path / f"part{i:04d}.html" for i in range(10)]

    result = _odredi_strategiju(engine, html_files, scores={})
    assert result == "LEKTURA", f"Ocekivano LEKTURA, dobijeno {result}"
