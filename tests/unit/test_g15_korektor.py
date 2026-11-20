"""G15: determinisicke zastite od pretjeranog KOREKTORA."""
import inspect

from processing import pipeline as P

OSN = ("<p>Jorg je rekao Katherine da su stigli u Ankrath tek u tri sata, "
       "a Makin je već čekao na vratima s dvanaest ljudi i jednim starim psom.</p>")


def test_ista_verzija_prolazi():
    assert P._kor_pretjeran(OSN, OSN) == (False, "")


def test_sitna_ispravka_prolazi():
    nova = OSN.replace("tek u tri", "tek oko tri")
    assert P._kor_pretjeran(OSN, nova)[0] is False


def test_prepisivanje_odbija():
    nova = ("<p>Nakon dugog puta stigli su napokon u grad, gdje ih je dočekao "
            "netko poznat, a ostali su se razišli po kućama bez ikakve riječi više.</p>")
    odb, razlog = P._kor_pretjeran(OSN, nova)
    assert odb and "%" in razlog or "imena" in razlog


def test_promjena_broja_odbija():
    nova = OSN.replace("dvanaest", "dvadeset").replace("tri sata", "4 sata")
    nova_s_brojem = OSN.replace("u tri", "u 3")
    assert P._kor_pretjeran(OSN, nova_s_brojem)[0] is True
    assert P._kor_pretjeran("<p>Bilo ih je 12 u sobi i svi su šutjeli dugo vremena.</p>",
                            "<p>Bilo ih je 21 u sobi i svi su šutjeli dugo vremena.</p>") == (True, "brojevi promijenjeni")


def test_nestanak_imena_odbija():
    a = ("<p>Rekao sam da su Jorg, Makin, Rike, Gorgoth i Katherine otišli u Ankrath "
         "jer su se svi bojali da će Sageous doći sam.</p>")
    b = ("<p>Rekao sam da su on, taj čovjek, oni drugi, onaj veliki i ona otišli u grad "
         "jer su se svi bojali da će doći sam.</p>")
    odb, razlog = P._kor_pretjeran(a, b)
    assert odb


def test_korektor_u_oba_mjesta():
    assert "_kor_pretjeran(pre_korektor, kor)" in inspect.getsource(P.process_chunk_with_ai)
    src = inspect.getsource(P)
    assert "_kor_pretjeran(pre_korektor_l, kor_l)" in src
