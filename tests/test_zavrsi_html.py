from pathlib import Path

from core import zavrsi


def _wd(tmp_path, tekst, text_dir=False):
    wd = tmp_path / "_skr_x"
    (wd / "checkpoints").mkdir(parents=True)
    d = wd / "text" if text_dir else wd
    d.mkdir(exist_ok=True)
    (d / "a.html").write_text("<html><body>" + tekst + "</body></html>", encoding="utf-8")
    return wd, d / "a.html"


ISP = [{"id": "t1", "fajl": "a.html", "blok": 0,
        "staro": "Ona je rekla da ne ide", "novo": "Ona rece da ne ide"}]


def test_html_primjena_i_idempotentnost(tmp_path):
    wd, f = _wd(tmp_path, "<p>Ona je <em>rekla</em> da ne ide.</p>")
    r = zavrsi.primijeni_u_html(wd / "checkpoints", ISP, bdir=tmp_path / "bk", log=lambda m: None)
    assert r == {"ok": 1, "vec": 0, "fail": 0}
    assert "Ona rece da ne ide" in f.read_text("utf-8")
    assert (tmp_path / "bk" / "html_a.html").exists()
    r2 = zavrsi.primijeni_u_html(wd / "checkpoints", ISP, log=lambda m: None)
    assert r2["vec"] == 1 and r2["ok"] == 0


def test_html_u_text_podmapi_i_nejednoznacno(tmp_path):
    wd, f = _wd(tmp_path, "<p>Ona je rekla da ne ide. Ona je rekla da ne ide.</p>", text_dir=True)
    r = zavrsi.primijeni_u_html(wd / "checkpoints", ISP, log=lambda m: None)
    assert r["fail"] == 1 and r["ok"] == 0
    assert "rece" not in f.read_text("utf-8")
    wd2, f2 = _wd(tmp_path / "b", "<p>Ona je rekla da ne ide.</p>", text_dir=True)
    assert zavrsi.primijeni_u_html(wd2 / "checkpoints", ISP, log=lambda m: None)["ok"] == 1
