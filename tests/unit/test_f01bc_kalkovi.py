import pathlib


def test_nema_praznih_zamjena_u_kalkovi_da():
    from core.kalkovi import kalkovi_da
    for i, e in enumerate(kalkovi_da.KALKOVI):
        assert isinstance(e, tuple) and len(e) >= 2, (i, e)
        assert callable(e[1]) or (isinstance(e[1], str) and e[1].strip()), (i, e)


def test_reload_ne_prazni_engine():
    from core.kalkovi import reload_dinamicki_kalkove
    from core.kalkovi.engine import kalkovi_engine
    n0 = kalkovi_engine.broj_patterna
    n1 = reload_dinamicki_kalkove()
    assert n0 >= 500
    assert n1 == n0 == kalkovi_engine.broj_patterna
    t, n = kalkovi_engine.primijeni("Deca su došla.")
    assert t == "Djeca su došla." and n == 1


def test_ispravan_tekst_ostaje_netaknut():
    from core.kalkovi.engine import kalkovi_engine
    for s in ("Znam da dolazim.", "Mislim da idem kući.", "Rekao je da će doći."):
        t, n = kalkovi_engine.primijeni(s)
        assert t == s and n == 0, (s, t, n)


def test_retro_pise_chk_samo_kad_se_tekst_promijenio():
    src = pathlib.Path("processing/retro.py").read_text(encoding="utf-8")
    assert "tekst_kor != tekst_orig" in src


def test_run_reload_koristi_reload_dinamicki_kalkove():
    src = pathlib.Path("run.py").read_text(encoding="utf-8")
    assert "reload_dinamicki_kalkove" in src
