"""J2: rod pripovjedaca po poglavlju uz zadanu vrijednost knjige (V1 i V2)."""
import inspect
import json
from types import SimpleNamespace

from processing import pipeline as P

ZENA = "\u017d"
M3 = "<p>Bio sam miran, rekao sam to i otišao sam kući.</p>"
Z3 = "<p>Bila sam miran, rekla sam to i otišla sam kući.</p>"


def _eng(tmp_path):
    return SimpleNamespace(log=lambda *a, **k: None, checkpoint_dir=tmp_path)


def _knjiga_m(tmp_path, n=4):
    for i in range(n):
        (tmp_path / f"p0_blok_{i}.chk").write_text(M3, "utf-8")


def test_zadani_rod_knjige_iz_chk(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    assert P._prip_knjiga_rod(e) == "M"
    assert "Dosadašnji tekst ove knjige pripovijeda MUŠKARAC" in P._prip_upute(e, "p1")


def test_nejasan_blok_ide_prema_knjizi(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    out = P._prip_korak(e, "<p>Rekla sam mu istinu, a onda sam bio miran.</p>", "p1", 0)
    assert "Rekao sam" in out


def test_jasan_zenski_blok_ostaje_i_oznaci_se(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    P._prip_korak(e, M3, "p1", 0)  # poglavlje postaje M
    out = P._prip_korak(e, Z3, "p1", 1)
    assert "Bila sam" in out and "rekla sam" in out  # nije prisilno M
    hr = json.loads((tmp_path / "human_review.json").read_text("utf-8"))
    assert any(x["stem"] == "p1_blok_1" for x in hr)


def test_zenski_blok_u_zenskom_poglavlju_bez_oznake(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    P._prip_korak(e, Z3, "p2", 0)
    P._prip_korak(e, Z3, "p2", 1)
    assert not (tmp_path / "human_review.json").exists()


def test_idempotentno(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    t = "<p>Rekla sam mu istinu, a onda sam bio miran.</p>"
    a = P._prip_korak(e, t, "p3", 0)
    assert P._prip_korak(e, a, "p3", 0) == a


def test_v1_i_v2_zovu_korak():
    assert "_prip_korak(self, finalno" in inspect.getsource(P._primijeni_kalkove_i_validator)
    src = inspect.getsource(P.process_chunk_with_retry)
    assert "_prip_korak(self, tekst" in src and "_prip_upute(self, file_name)" in src


def test_imenice_nisu_participi(tmp_path):
    _knjiga_m(tmp_path)
    e = _eng(tmp_path)
    t = "<p>Bio sam miran, a ti si bila budala; vidjeli smo vješala, ali sam rekao ne.</p>"
    out = P._prip_korak(e, t, "p4", 0)
    assert "budala" in out and "vješala" in out
