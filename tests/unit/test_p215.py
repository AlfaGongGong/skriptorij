from core.gate_provjere import cir2lat, gate_blok
from core.poravnanje import recenice
from core.sidro import sidro_za_nalaz

EN = ("The old man walked slowly down the road toward the village. He carried a heavy sack over his shoulder. "
      "The hangman asked of the carrion crow where the dead men lay. Night fell upon the empty fields and silence followed.")
HR = ("Starac je polako hodao cestom prema selu i nije se osvrtao. Preko ramena je nosio težak kovčeg nabijen željezom. "
      "Noć se spustila na prazna polja i nastupila je duboka tišina.")


def test_cir2lat():
    assert cir2lat("Љубав и смрт, Џон") == "Ljubav i smrt, Džon"


def test_gate_ekav():
    t, info = gate_blok("<p>Dete je lepo.</p>")
    assert "ekavizmi" in info


def test_izostavljeno():
    r = sidro_za_nalaz("izostavljeno", "The hangman asked of the carrion crow", "", EN, HR)
    assert r and "hangman" in r["en"] and r["hr"] in HR


def test_dodano():
    hr = "Starac je polako hodao cestom prema selu. Nosio je težak kovčeg preko ramena. Bio je to dan kakav se rijetko pamti."
    s = recenice(hr)
    r = sidro_za_nalaz("dodano", "", s[2], "", hr)
    assert r and r["novo"] == s[1]
