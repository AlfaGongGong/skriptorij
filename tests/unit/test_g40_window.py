"""G40: sliding window je 1 uz jedan aktivni kljuc."""
import types
from processing.parallel import AdaptiveParallelism


def _w(n):
    fleet = types.SimpleNamespace(get_total_active_keys=lambda: n)
    return AdaptiveParallelism(types.SimpleNamespace(fleet=fleet))._get_window_size()


def test_window_po_kljucevima():
    assert _w(0) == 1
    assert _w(1) == 1
    assert _w(2) == 2
    assert _w(8) == 3
