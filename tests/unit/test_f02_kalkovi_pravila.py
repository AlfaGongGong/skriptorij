def _p(s):
    from core.kalkovi.engine import kalkovi_engine
    return kalkovi_engine.primijeni(s)[0]


def test_da_pravila_ne_diraju_prezent():
    for s in ("Prisili ga da radi.", "Pomogao mu je da ode.", "Bio je u stanju da ode.",
              "Pokušao je da pobjegne.", "Znam da dolazim.", "Mislim da idem kući."):
        assert _p(s) == s, (s, _p(s))


def test_cekati_sjetiti_spustiti_ostaju():
    for s in ("Čekao je na njega.", "Ona se sjetila toga.", "Sjetio se toga.", "Spusti dolje oružje."):
        assert _p(s) == s, (s, _p(s))


def test_nije_valjda_i_stara_ruševina_ostaju():
    for s in ("Nije valjda otišao?", "Vidio je staru ruševinu.", "Njegova stara ruševina je pala."):
        assert _p(s) == s, (s, _p(s))


def test_ekavizmi_i_dalje_rade():
    assert _p("Deca su došla.") == "Djeca su došla."
    assert _p("Ko je to?") == "Tko je to?"


def test_mrtva_funkcija_m_obrisana():
    from core.kalkovi import kalkovi_da
    assert not hasattr(kalkovi_da, "_m")


def test_text_utils_ne_ostavlja_prezent():
    from core.text_utils import _automatska_korekcija
    for s in ("<p>Odlučio je da ode.</p>", "<p>Morao je da ode.</p>", "<p>Bio je u stanju da ode.</p>"):
        assert _automatska_korekcija(s) == s, s
