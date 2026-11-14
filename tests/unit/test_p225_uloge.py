import json
import types
import zipfile

from core import glosar_ekstrakcija as ge


def test_prebroji_uloge():
    c = ge.prebroji_uloge("The valet bowed. Two valets came. A Butler, the butler's hat. maids")
    assert c == {"valet": 2, "butler": 2, "maid": 1}


def _epub(p, tekst):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("OEBPS/chapter001.xhtml", "<html><body><p>" + tekst + "</p></body></html>")
        z.writestr("content.opf", "<package><dc:language>en</dc:language></package>")


def test_dopuni_uloge(tmp_path, monkeypatch):
    from core.engine import SkriptorijAllInOne as E

    kd = tmp_path / "kanon"
    kd.mkdir()
    monkeypatch.setenv("BOOKLYFI_KANON_DIR", str(kd))
    ep = tmp_path / "Knjiga.epub"
    _epub(ep, "The valet came. The valet sat. A valet left. The butler waited once. " * 3 + "The quick brown fox jumps over the lazy dog and the cat sleeps in the sun. " * 20)
    (kd / "Knjiga.json").write_text(json.dumps({"knjiga": "Knjiga", "termini": {"Lyon": {"hr": "Lyon"}}}), encoding="utf-8")
    poz = []

    def lazni(jezik, batch, fleet, sistem=None):
        poz.append(list(batch))
        return {"valet": {"kategorija": "termin", "hr": "sobar"}}

    monkeypatch.setattr(ge, "posalji_ai_batch", lazni)
    monkeypatch.setattr(ge, "detektuj_jezik", lambda p: "EN")
    s = types.SimpleNamespace(book_path=str(ep), fleet=object(), log=lambda *a, **k: None)
    assert E._dopuni_uloge_kanon(s) is True
    d = json.loads((kd / "Knjiga.json").read_text(encoding="utf-8"))
    assert d["termini"]["valet"]["hr"] == "sobar" and d["uloge_provjerene"] is True
    assert "Lyon" in d["termini"]
    assert poz == [["butler", "valet"]]
    assert E._dopuni_uloge_kanon(s) is True and len(poz) == 1
