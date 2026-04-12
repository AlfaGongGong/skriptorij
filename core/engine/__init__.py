"""Engine paket — processing pipeline."""
# Thin wrapper koji re-eksportuje ulazne tačke iz skriptorij.py
from skriptorij import start_skriptorij_from_master

__all__ = ["start_skriptorij_from_master"]
