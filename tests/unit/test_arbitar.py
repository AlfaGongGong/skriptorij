from core.arbitar import (nadji_u_raw, nove_rijeci, parsiraj_odgovor, predfilter,
                          primijeni, provjeri_zamjenu)


def test_predfilter_odbacuje_samoopovrgnute():
    assert predfilter({"hr_fragment": "x", "objasnjenje": "Točno."})[0] is False
    assert predfilter({"hr_fragment": "x", "objasnjenje": "Anus i čmar su sinonimi u ovom kontekstu, prihvatljivo."})[0] is False
    assert predfilter({"hr_fragment": "x", "objasnjenje": "Provjerit ću ostalo."})[0] is False


def test_predfilter_propusta_stvarne():
    ok, _ = predfilter({"hr_fragment": "pogrebnim kolačima", "objasnjenje": "Prijevod je potpuno pogrešan."})
    assert ok
    ok, _ = predfilter({"hr_fragment": "x", "objasnjenje": "Točnije bi bilo: nešto drugo."})
    assert ok


def test_predfilter_prazan_hr():
    assert predfilter({"hr_fragment": "", "objasnjenje": "Negacija je izgubljena."}) == (False, "prazan_hr_fragment")


def test_nadji_jednom_i_granice_rijeci():
    raw = "<p>Tata i tatam su otišli. Vidio sam tata, pa tata.</p>"
    assert nadji_u_raw(raw, "tatam") is not None     # jedna pojava, "tata" unutar "tatam" se ne broji
    assert nadji_u_raw(raw, "Tata") is not None      # velika slova se razlikuju
    assert nadji_u_raw(raw, "tata") is None          # dvije pojave
    assert nadji_u_raw(raw, "nema ga") is None


def test_nadji_ne_prelazi_oznake():
    raw = "<p>pogrebnim <em>kolačima</em> kroz grad</p>"
    assert nadji_u_raw(raw, "pogrebnim kolačima") is None


def test_nadji_tolerantan_na_razmake():
    raw = "<p>gurnu prst\nu čmar</p>"
    assert nadji_u_raw(raw, "gurnu prst u čmar") is not None


def test_primijeni():
    raw = "<p>Vidio sam pogrebnim kolačima put.</p>"
    assert primijeni(raw, "pogrebnim kolačima", "pogrebnim kolima") == "<p>Vidio sam pogrebnim kolima put.</p>"
    assert primijeni(raw, "nepostojece", "x") is None


def test_provjeri_zamjenu():
    rj = {"pogrebnim", "kolima", "kolačima", "put"}
    assert provjeri_zamjenu("pogrebnim kolačima", "pogrebnim kolima", rj) == (True, "")
    ok, r = provjeri_zamjenu("pogrebnim kolačima", "pogrebnim Zatulumtalo", rj)
    assert not ok and r.startswith("nova_rijec")
    assert provjeri_zamjenu("a", "a", rj)[0] is False
    assert provjeri_zamjenu("pogrebnim kolačima", "<b>kolima</b>", rj)[0] is False
    assert provjeri_zamjenu("pogrebnim kolačima", "", rj)[0] is False
    assert provjeri_zamjenu("pogrebnim kolačima", "kolima kolima kolima kolima kolima kolima kolima kolima", rj)[0] is False


def test_nove_rijeci_ignorira_stare_iz_fragmenta():
    assert nove_rijeci("a b c", "a b", {"c"}) == []
    assert nove_rijeci("a x", "a", set()) == ["x"]


def test_parsiraj_odgovor():
    d = parsiraj_odgovor('Evo: {"presuda": "stvarna_greska", "zamjena": "kolima", "razlog": "r"} kraj')
    assert d == {"presuda": "stvarna_greska", "zamjena": "kolima", "razlog": "r"}
    assert parsiraj_odgovor('{"presuda": "nesto"}') is None
    assert parsiraj_odgovor("nema jsona") is None
    assert parsiraj_odgovor('{"presuda": "lazni_alarm"}')["zamjena"] == ""


def test_provjeri_zamjenu_bez_rijecnika_ne_provjerava_nove_rijeci():
    assert provjeri_zamjenu("zapsala se", "uvukla se", None) == (True, "")
    assert provjeri_zamjenu("a", "a", None)[0] is False


def test_slijepi_parseri():
    from core.arbitar import parsiraj_provjera, parsiraj_slijepo, parsiraj_zamjena, prompt_slijepo
    d = parsiraj_slijepo('x {"moj_smisao":"m","presuda":"razlicito","razlog":"r"} y')
    assert d["presuda"] == "razlicito" and d["moj_smisao"] == "m"
    assert parsiraj_slijepo('{"presuda":"stvarna_greska"}') is None
    assert parsiraj_zamjena('{"zamjena":" kolima "}') == {"zamjena": "kolima"}
    assert parsiraj_zamjena("nema") is None
    assert parsiraj_provjera('{"vjernije": true, "izmisljene_rijeci": ["x"]}') == {"vjernije": True, "izmisljene": ["x"]}
    assert parsiraj_provjera('{"vjernije": "da"}') is None
    assert "verifikator" not in prompt_slijepo("a", "b", "c").lower()
