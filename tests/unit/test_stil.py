# -*- coding: utf-8 -*-
import json
import zipfile

from core import stil


def test_recenice_kratice():
    assert stil._recenice("Mr. Smith went home. He slept.") == ["Mr. Smith went home.", "He slept."]


def test_izmjeri_osnovno():
    odl = ["“Go home,” he said. She did not.", "The night was long and cold.", "“No.”"]
    p = stil.izmjeri(odl, "en")
    assert p["n_recenica"] == 4
    assert p["dijalog_odlomaka_pct"] == 66.7
    assert p["navodnik_pct_dijaloga"] == 100.0


def test_pasiv_en():
    p = stil.izmjeri(["The door was opened by him. He opened the door."], "en")
    assert p["pasiv_pct"] == 50.0


def test_hr_crtica_bez_pasiva_i_fraza():
    p = stil.izmjeri(["— Dobar dan.", "Tekst je ovdje."], "hr")
    assert p["dijalog_odlomaka_pct"] == 50.0
    assert p["crtica_pct_dijaloga"] == 100.0
    assert p["pasiv_pct"] is None
    assert p["fraze"] == []


def test_fraze_en():
    p = stil.izmjeri([" ".join(["He walked down the old road."] * 6)], "en")
    assert any(f == "walked down the" for f, _ in p["fraze"])


def test_prazno():
    p = stil.izmjeri([], "en")
    assert p["n_recenica"] == 0


def _epub(tmp_path):
    put = tmp_path / "t.epub"
    with zipfile.ZipFile(put, "w") as z:
        z.writestr("OEBPS/ch1.xhtml", "<html><body><p>He <i>did</i> go.</p><p>“Hi.”</p></body></html>")
        z.writestr("OEBPS/nav.xhtml", "<html><body><p>skip me</p></body></html>")
    return put


def test_izdvoji_odlomke(tmp_path):
    assert stil.izdvoji_odlomke(_epub(tmp_path)) == ["He did go.", "“Hi.”"]


def test_izmjeri_epube_i_spremi(tmp_path):
    prof = stil.izmjeri_epube([_epub(tmp_path)], "Joe Abercrombie", "en")
    assert prof["autor"] == "Joe Abercrombie" and prof["izvori"][0]["odlomaka"] == 2
    p = stil.spremi(prof, "Joe Abercrombie", "en", root=tmp_path)
    assert p == tmp_path / "data" / "stil" / "joe_abercrombie.json"
    assert json.loads(p.read_text("utf-8"))["n_recenica"] == prof["n_recenica"]
    assert stil.spremi(prof, "Joe Abercrombie", "hr", root=tmp_path).name == "joe_abercrombie_hr.json"


def test_slug():
    assert stil.slug("Žarko Čović") == "zarko_covic"
    assert stil.slug("") == "nepoznat_autor"
