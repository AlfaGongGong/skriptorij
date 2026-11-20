"""G37: finalize je fail-closed kad spajanje .chk padne ili nema _skr_ za prijevod."""
import types
import pytest
from epub import packager as P


def _stub(tmp_path, knjiga_mode=None):
    s = types.SimpleNamespace()
    s.work_dir = tmp_path / "w"; s.work_dir.mkdir()
    s.checkpoint_dir = tmp_path / "w" / "checkpoints"
    s.out_path = tmp_path / "out.epub"
    s.book_path = tmp_path / "b.epub"
    s.clean_book_name = "x"
    s.shared_stats = {"knjiga_mode": knjiga_mode} if knjiga_mode else {}
    s.log = lambda *a, **k: None
    return s


def test_pad_spajanja_prekida(tmp_path, monkeypatch):
    def boom(e): raise ValueError("pad")
    monkeypatch.setattr(P, "_spoji_chk_u_html", boom)
    monkeypatch.setattr(P, "_finaliziraj_fix_epub", lambda s: None)
    monkeypatch.delenv("BOOKLYFI_FINALIZE_OTVORENO", raising=False)
    s = _stub(tmp_path)
    with pytest.raises(RuntimeError):
        P.finalize(s)
    assert s.shared_stats.get("status") != "ZAVRŠENO"


def test_nema_skr_uz_prijevod_prekida(tmp_path, monkeypatch):
    def nema(e): e._spoji_bez_skr = True; return 0
    monkeypatch.setattr(P, "_spoji_chk_u_html", nema)
    monkeypatch.setattr(P, "_finaliziraj_fix_epub", lambda s: None)
    monkeypatch.delenv("BOOKLYFI_FINALIZE_OTVORENO", raising=False)
    with pytest.raises(RuntimeError):
        P.finalize(_stub(tmp_path, knjiga_mode="X"))


def test_nema_skr_bez_prijevoda_prolazi(tmp_path, monkeypatch):
    def nema(e): e._spoji_bez_skr = True; return 0
    monkeypatch.setattr(P, "_spoji_chk_u_html", nema)
    monkeypatch.setattr(P, "_finaliziraj_fix_epub", lambda s: None)
    monkeypatch.setattr(P, "_get_output_dir", lambda: tmp_path / "o")
    s = _stub(tmp_path)
    P.finalize(s)
    assert s.shared_stats["status"] == "ZAVRŠENO"
