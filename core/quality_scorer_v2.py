# core/quality_scorer_v2.py — Nezavisni scorer

import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCORER_PRIORITETI = {
    "gemini": ["groq", "cerebras", "mistral", "cohere"],
    "groq": ["gemini", "cerebras", "mistral"],
    "cerebras": ["gemini", "groq", "mistral"],
    "mistral": ["gemini", "groq", "cerebras"],
    "cohere": ["gemini", "groq", "mistral"],
    "sambanova": ["gemini", "groq", "cerebras"],
    "openrouter": ["gemini", "groq", "mistral"],
    "chutes": ["gemini", "groq", "cerebras"],
    "unknown": ["gemini", "groq", "cerebras"],
}

class TranslatorTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self._stats: dict[str, int] = {}

    def zabilježi(self, file_name: str, chunk_idx: int, provider: str) -> None:
        if not provider:
            return
        norm = _normaliziraj_provider(provider)
        stem = f"{file_name}_blok_{chunk_idx}"
        with self._lock:
            self._data[stem] = norm
            self._stats[norm] = self._stats.get(norm, 0) + 1

    def dohvati(self, file_name: str, chunk_idx: int) -> Optional[str]:
        stem = f"{file_name}_blok_{chunk_idx}"
        with self._lock:
            return self._data.get(stem)

    def statistike(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

_tracker = TranslatorTracker()

def get_tracker() -> TranslatorTracker:
    return _tracker

def zabilježi_prevoditelja(file_name: str, chunk_idx: int, engine_label: str) -> None:
    _tracker.zabilježi(file_name, chunk_idx, engine_label)

def _normaliziraj_provider(provider: str) -> str:
    if not provider:
        return "unknown"
    p = provider.lower().strip()
    if p.startswith("v2/"):
        parts = p.split("/")
        if len(parts) >= 2:
            return parts[1]
    for known in ["gemini", "groq", "cerebras", "mistral", "cohere",
                  "sambanova", "openrouter", "chutes"]:
        if known in p:
            return known
    return "unknown"

def _odaberi_scorer_provider(prevodilac_provider: str) -> Optional[str]:
    norm = _normaliziraj_provider(prevodilac_provider or "unknown")
    kandidati = _SCORER_PRIORITETI.get(norm, _SCORER_PRIORITETI["unknown"])
    for k in kandidati:
        if k != norm:
            return k
    return None

def get_scorer_sys_override(
    self_obj, prevodilac_provider, chunk_idx, file_name
) -> Optional[str]:
    if not prevodilac_provider:
        prevodilac_provider = _tracker.dohvati(file_name, chunk_idx)
    if not prevodilac_provider:
        return None

    scorer_provider = _odaberi_scorer_provider(prevodilac_provider)
    if not scorer_provider:
        return None

    try:
        fleet = getattr(self_obj, "fleet", None)
        if fleet is None:
            return None
        dostupni = set()
        if hasattr(fleet, "keys"):
            for k in fleet.keys():
                dostupni.add(_normaliziraj_provider(str(k)))
        if scorer_provider in dostupni:
            logger.debug(f"Scorer override: {prevodilac_provider} → {scorer_provider}")
            return f"__FORCE_PROVIDER__{scorer_provider}__"
    except Exception:
        pass
    return None
