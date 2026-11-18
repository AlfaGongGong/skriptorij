# -*- coding: utf-8 -*-
import asyncio
import json

from processing import verifier_tocka as vt


class FakeSelf:
    def __init__(self, tmp, odgovori):
        self.checkpoint_dir = tmp
        self.odgovori = list(odgovori)
        self.pozivi = []
        self.logovi = []

    def _atomic_write(self, p, t):
        p.write_text(t, "utf-8")

    def log(self, m, lvl="info"):
        self.logovi.append(m)

    async def _call_ai_engine(self, prompt, idx, **kw):
        self.pozivi.append((prompt, kw))
        return (self.odgovori.pop(0), "FAKE")


GR = {"tip": "kriv_smisao", "en_fragment": "deathly composure",
      "hr_fragment": "smrt noća mirnost", "objasnjenje": "pogresan smisao"}
OUT = {"verifier": "flags", "n": 1, "score": 7.5, "greske": [GR]}
EN = "<p>deathly composure fell.</p>"


def _chk(tmp, tijelo):
    (tmp / "poglavlje_blok_3.chk").write_text(
        "<!-- chunk_sha: abc -->\n" + tijelo, "utf-8")


def _pokreni(s, out=OUT):
    return asyncio.run(vt.tocka_popravak(s, out, EN, "blok", 3, "poglavlje", "narativ", {}))


def test_kandidati_filtrira():
    gr = [GR, GR,
          {"tip": "izostavljeno", "en_fragment": "a", "hr_fragment": "", "objasnjenje": ""},
          {"tip": "dodano", "en_fragment": "", "hr_fragment": "b", "objasnjenje": ""},
          {"tip": "broj", "en_fragment": "ten", "hr_fragment": "devet", "objasnjenje": ""}]
    k = vt.kandidati(gr)
    assert [x["hr"] for x in k] == ["smrt noća mirnost", "devet"]


def test_parse_odgovor():
    assert vt.parse_odgovor('{"hr": "novo"}') == "novo"
    assert vt.parse_odgovor('```json\n{"hr": ""}\n```') == ""
    assert vt.parse_odgovor('Evo: {"hr": "x y"} gotovo') == "x y"
    assert vt.parse_odgovor("nije json") is None
    assert vt.parse_odgovor('{"drugo": 1}') is None


def test_primijeni_zamjenu():
    t = "<p>Pala je smrt noća mirnost.</p>"
    novo, r = vt.primijeni_zamjenu(t, "smrt noća mirnost", "smrtno mirno držanje")
    assert r == "" and "smrtno mirno držanje" in novo and novo.startswith("<p>")
    assert vt.primijeni_zamjenu(t + t, "smrt noća mirnost", "xx yy zz aa bb")[1] == "vise_pojava"
    assert vt.primijeni_zamjenu(t, "nema ga", "xx")[1] == "nema_pojave"
    assert vt.primijeni_zamjenu(t, "smrt noća mirnost", "<i>x</i>")[1] == "html_u_novom"
    assert vt.primijeni_zamjenu(t, "smrt noća mirnost", "a")[1].startswith("duljina")
    assert vt.primijeni_zamjenu(t, "smrt noća mirnost", "smrt noća mirnost")[1] == "isto"


def test_primijeni_escape():
    t = "<p>Tom &amp; Jerry su otisli.</p>"
    novo, r = vt.primijeni_zamjenu(t, "Tom & Jerry su otisli", "Tom & Jerry su otišli")
    assert r == "" and "Tom &amp; Jerry su otišli" in novo


def test_podijeli():
    z, t = vt.podijeli("<!-- chunk_sha: abc -->\n<p>x</p>")
    assert z.startswith("<!--") and t == "<p>x</p>"
    assert vt.podijeli("<p>x</p>") == ("", "<p>x</p>")


def test_ukljucena(monkeypatch):
    monkeypatch.delenv("BOOKLYFI_VERIFIER_TOCKA", raising=False)
    monkeypatch.delenv("BOOKLYFI_VERIFIER_FIX", raising=False)
    assert vt.ukljucena() is False
    monkeypatch.setenv("BOOKLYFI_VERIFIER_FIX", "1")
    assert vt.ukljucena() is True
    monkeypatch.setenv("BOOKLYFI_VERIFIER_TOCKA", "0")
    assert vt.ukljucena() is False


def test_uspjeh(tmp_path):
    _chk(tmp_path, "<p>Pala je smrt noća mirnost.</p>")
    s = FakeSelf(tmp_path, ['{"hr": "smrtno mirno držanje"}', '{"ok": true, "greske": []}'])
    res = _pokreni(s)
    assert res["verifier"] == "ok"
    novo = (tmp_path / "poglavlje_blok_3.chk").read_text("utf-8")
    assert novo.startswith("<!-- chunk_sha: abc -->\n") and "smrtno mirno držanje" in novo
    assert (tmp_path / "verifier_prije" / "poglavlje_blok_3.chk.tocka.txt").exists()
    z = json.loads((tmp_path / "quality_verifier.json").read_text("utf-8"))["blok"]
    assert z["tocka"]["popravljeno"] == 1 and z["oznaka"] == "ok" and z["oznaka_prije"] == "sumnjiv"


def test_nije_bolji(tmp_path):
    _chk(tmp_path, "<p>Pala je smrt noća mirnost.</p>")
    stari = (tmp_path / "poglavlje_blok_3.chk").read_text("utf-8")
    ver = json.dumps({"ok": False, "greske": [{
        "tip": "kriv_smisao", "en_fragment": "deathly composure",
        "hr_fragment": "smrtno mirno držanje", "objasnjenje": "x"}]})
    s = FakeSelf(tmp_path, ['{"hr": "smrtno mirno držanje"}', ver])
    res = _pokreni(s)
    assert res is OUT
    assert (tmp_path / "poglavlje_blok_3.chk").read_text("utf-8") == stari
    z = json.loads((tmp_path / "quality_verifier.json").read_text("utf-8"))["blok"]
    assert z["tocka"]["razlog"] == "nije_bolji"


def test_vec_ispravno_bez_ponovne_verifikacije(tmp_path):
    _chk(tmp_path, "<p>Pala je smrt noća mirnost.</p>")
    s = FakeSelf(tmp_path, ['{"hr": ""}'])
    res = _pokreni(s)
    assert res is OUT and len(s.pozivi) == 1
    z = json.loads((tmp_path / "quality_verifier.json").read_text("utf-8"))["blok"]
    assert z["tocka"]["vec_ispravno"] == 1


def test_vise_pojava_ne_zove_model(tmp_path):
    _chk(tmp_path, "<p>smrt noća mirnost</p><p>smrt noća mirnost</p>")
    s = FakeSelf(tmp_path, [])
    res = _pokreni(s)
    assert res is OUT and s.pozivi == []


def test_nema_chk(tmp_path):
    s = FakeSelf(tmp_path, [])
    assert _pokreni(s) is OUT and s.pozivi == []
