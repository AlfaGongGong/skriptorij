import random

from epub.styler import _je_duplikat_slijed


def _tekst(n):
    return " ".join("w%d" % i for i in range(n))


def test_identican_je_duplikat():
    t = _tekst(200)
    assert _je_duplikat_slijed(t, t)


def test_isti_rijecnik_drugi_slijed_nije_duplikat():
    rijeci = _tekst(300).split()
    mijesano = rijeci[:]
    random.Random(2).shuffle(mijesano)
    assert not _je_duplikat_slijed(" ".join(rijeci), " ".join(mijesano))


def test_kratki_blok_iz_duzeg_s_drugim_slijedom_nije_duplikat():
    rijeci = _tekst(1700).split()
    kratki = rijeci[:450]
    random.Random(3).shuffle(kratki)
    assert not _je_duplikat_slijed(" ".join(kratki), " ".join(rijeci))


def test_stvarni_preklop_je_duplikat():
    a = _tekst(300)
    duzi = a + " " + " ".join("x%d" % i for i in range(300))
    assert _je_duplikat_slijed(a, duzi)


def test_oznake_se_ignoriraju():
    assert _je_duplikat_slijed("<p>jedan dva tri cetiri</p>", "jedan dva tri cetiri")


def test_prazno_nije_duplikat():
    assert not _je_duplikat_slijed("", "nesto tu je")
