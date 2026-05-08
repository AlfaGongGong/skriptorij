"""
core/validators/__init__.py
────────────────────────────
Registar svih BooklyFi validatora.
"""

from core.validators.morfo_validator import MorfoValidator, validiraj_tekst

__all__ = [
    "MorfoValidator",
    "validiraj_tekst",
]
