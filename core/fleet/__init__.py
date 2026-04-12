"""Fleet paket — upravljanje API ključevima."""
# Re-eksportuje klase iz api_fleet.py za novi modularni import
from api_fleet import (
    FleetManager,
    _KeyState as KeyState,
    register_active_fleet,
    get_active_fleet,
    _DEFAULT_MODELS as DEFAULT_MODELS,
    _COOLDOWN_429 as COOLDOWN_429,
    _COOLDOWN_ERROR as COOLDOWN_ERROR,
)

__all__ = [
    "FleetManager",
    "KeyState",
    "register_active_fleet",
    "get_active_fleet",
    "DEFAULT_MODELS",
    "COOLDOWN_429",
    "COOLDOWN_ERROR",
]
