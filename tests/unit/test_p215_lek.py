from core.lektura_provjera import izostavljeno

ULAZ = ("Starac je polako hodao cestom prema selu i nije se osvrtao. "
        "Preko ramena je nosio težak kovčeg nabijen željezom i sjajnim kopčama. "
        "Noć se spustila na prazna polja i nastupila je duboka tišina. "
        "U daljini se oglasio pas, a zatim je opet zavladao mir nad cijelom dolinom. "
        "Nitko nije znao kamo ide.")


def test_isto():
    r = izostavljeno(ULAZ, ULAZ)
    assert r["ispao"] == 0 and r["udio"] == 0.0


def test_ispala_recenica():
    izlaz = ULAZ.replace("Preko ramena je nosio težak kovčeg nabijen željezom i sjajnim kopčama. ", "")
    r = izostavljeno(ULAZ, izlaz)
    assert r["ispao"] == 1 and r["udio"] > 0.1, r


def test_lagana_lektura_nije_izostavljanje():
    izlaz = ULAZ.replace("polako", "sporo").replace("nastupila je duboka", "zavladala je duboka").replace("opet ", "")
    r = izostavljeno(ULAZ, izlaz)
    assert r["ispao"] == 0, r


def test_prazan_izlaz():
    assert izostavljeno(ULAZ, "<p></p>")["udio"] == 1.0
