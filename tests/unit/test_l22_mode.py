from core.mode_detekcija import mode_iz_izvora_en, odluci_mode

EN = ("<p>The old man did not look at the boy, but he said that they would not be there when "
      "you came back from the river, and it was what it was and we had been told about it.</p>\n") * 40
HR = ("<p>Stari čovjek nije pogledao dječaka, ali je rekao da ih neće biti kad se vratiš s rijeke, "
      "a to je bilo onako kako je bilo i svi su nam to već bili rekli.</p>\n") * 40


def _izvor(tmp_path, tekst, n=4):
    d = tmp_path / "izvor_en"
    d.mkdir()
    for i in range(n):
        (d / ("ch%d.html.en" % i)).write_text(tekst, encoding="utf-8")


def test_engleski_izvor_je_prevod(tmp_path):
    _izvor(tmp_path, EN)
    assert mode_iz_izvora_en(tmp_path) == "PREVOD"


def test_hrvatski_izvor_je_lektura(tmp_path):
    _izvor(tmp_path, HR)
    assert mode_iz_izvora_en(tmp_path) == "LEKTURA"


def test_bez_izvora_none(tmp_path):
    assert mode_iz_izvora_en(tmp_path) is None


def test_odluka_pragovi():
    assert odluci_mode(0.0, 0.124) == "PREVOD"
    assert odluci_mode(0.0, 0.09) == "PREVOD"
    assert odluci_mode(0.0, 0.03) == "LEKTURA"
    assert odluci_mode(0.01, 0.2) == "LEKTURA"
