"""G41: _spoji_chk_u_html ne prepisuje poglavlje kad .chk blokovi nisu uzastopni; finalize puca uz prijevod."""
import types
import pytest
from epub import packager as P


def _engine(tmp_path, chks, knjiga_mode=None):
    w = tmp_path / "w"; (w / "text").mkdir(parents=True)
    (w / "text" / "ch1.html").write_text("<html><body><p>ORIGINAL</p></body></html>", encoding="utf-8")
    c = w / "checkpoints"; c.mkdir()
    for i in chks:
        (c / f"ch1.html_blok_{i}.chk").write_text(f"<p>Prijevod {i}</p>", encoding="utf-8")
    e = types.SimpleNamespace(work_dir=w, checkpoint_dir=c, clean_book_name="x" * 40,
                              log=lambda *a, **k: None, shared_stats={"knjiga_mode": knjiga_mode} if knjiga_mode else {},
                              out_path=tmp_path / "o.epub", book_path=tmp_path / "b.epub")
    return e


def test_rupa_ne_prepisuje(tmp_path):
    e = _engine(tmp_path, [0, 2])
    P._spoji_chk_u_html(e)
    assert "ORIGINAL" in (e.work_dir / "text" / "ch1.html").read_text(encoding="utf-8")
    assert e._spoji_rupe == ["ch1.html"]


def test_uzastopni_prepisuje(tmp_path):
    e = _engine(tmp_path, [0, 1])
    P._spoji_chk_u_html(e)
    t = (e.work_dir / "text" / "ch1.html").read_text(encoding="utf-8")
    assert "Prijevod 0" in t and "Prijevod 1" in t
    assert not getattr(e, "_spoji_rupe", None)


def test_finalize_puca_uz_rupu_u_prijevodu(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_finaliziraj_fix_epub", lambda s: None)
    monkeypatch.delenv("BOOKLYFI_FINALIZE_OTVORENO", raising=False)
    e = _engine(tmp_path, [0, 2], knjiga_mode="X")
    with pytest.raises(RuntimeError):
        P.finalize(e)
