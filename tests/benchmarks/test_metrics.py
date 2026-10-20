import pytest

from core.metrics import compute_metrics

KLJUCEVI = {
    "ekavizmi_per_1000", "en_ostaci_per_1000", "duplikati",
    "ratio_source_target", "tipografija_greske", "reci_ukupno",
}


def _p(reci, kraj="."):
    return "<p>" + " ".join(reci) + kraj + "</p>"


def test_prazan_tekst():
    m = compute_metrics("")
    assert m["reci_ukupno"] == 0
    assert m["ekavizmi_per_1000"] == 0.0
    assert m["en_ostaci_per_1000"] == 0.0
    assert m["duplikati"] == 0
    assert m["tipografija_greske"] == 0
    assert m["ratio_source_target"] is None


def test_none_graceful():
    m = compute_metrics(None)
    assert m["reci_ukupno"] == 0
    assert m["ratio_source_target"] is None


def test_kljucevi_api():
    assert set(compute_metrics("<p>Lijepo vrijeme danas.</p>")) == KLJUCEVI


def test_jednostavan_hr_tekst():
    m = compute_metrics("<p>Lijepo vrijeme danas.</p>")
    assert m["reci_ukupno"] == 3
    assert m["ekavizmi_per_1000"] == 0.0
    assert m["en_ostaci_per_1000"] == 0.0
    assert m["duplikati"] == 0
    assert m["tipografija_greske"] == 0
    assert m["ratio_source_target"] is None


def test_ekavizmi_3_na_100_reci():
    tekst = _p(["Hteo", "smeo", "sedeo"] + ["lijepa"] * 97)
    m = compute_metrics(tekst)
    assert m["reci_ukupno"] == 100
    assert m["ekavizmi_per_1000"] == pytest.approx(30.0, abs=0.01)


def test_ekavizmi_preklapanje_broji_jednom():
    m = compute_metrics("<p>Pre nego što dođeš.</p>")
    assert 0 < m["ekavizmi_per_1000"] <= 250.0


def test_en_ostaci_50_posto():
    tekst = _p(["the"] * 50 + ["kuca"] * 50)
    m = compute_metrics(tekst)
    assert m["reci_ukupno"] == 100
    assert m["en_ostaci_per_1000"] == pytest.approx(500.0)


def test_duplikati_tri_ista_pasusa():
    p = "<p>Ovo je dovoljno dug pasus koji se ponavlja.</p>"
    m = compute_metrics(p * 3)
    assert m["duplikati"] == 2


def test_duplikati_kratki_pasusi_se_ignorisu():
    m = compute_metrics("<p>Da.</p><p>Da.</p><p>Da.</p>")
    assert m["duplikati"] == 0


def test_spec_primjer_duplikat_unutar_jednog_pasusa_nije_duplikat():
    text = "<p>On je rekao da će doći. On je rekao da će doći.</p><p>Lepo vreme.</p>"
    m = compute_metrics(text)
    assert m["reci_ukupno"] == 14
    assert m["duplikati"] == 0


def test_ratio_source_100_target_90():
    source = _p(["word"] * 100)
    text = _p(["rijec"] * 90)
    m = compute_metrics(text, source)
    assert m["ratio_source_target"] == pytest.approx(1.11, abs=0.01)


def test_ratio_none_bez_izvora_i_za_prazan_izvor():
    text = "<p>Lijepo vrijeme danas.</p>"
    assert compute_metrics(text)["ratio_source_target"] is None
    assert compute_metrics(text, "")["ratio_source_target"] is None
    assert compute_metrics(text, "   ")["ratio_source_target"] is None


def test_tipografija_nedostaje_razmak():
    m = compute_metrics("Ovo je recenica.Ovo je druga.")
    assert m["tipografija_greske"] >= 1


def test_tipografija_dupli_razmak():
    m = compute_metrics("<p>Ovo je  tekst.</p>")
    assert m["tipografija_greske"] >= 1


def test_tipografija_crtica_umjesto_em_dash():
    assert compute_metrics("<p>- Dobar dan.</p>")["tipografija_greske"] >= 1
    assert compute_metrics("<p>\u2014 Dobar dan.</p>")["tipografija_greske"] == 0


def test_tipografija_malo_slovo_iza_tacke():
    m = compute_metrics("<p>Ovo je prva. ovo je druga.</p>")
    assert m["tipografija_greske"] >= 1


def test_tipografija_skracenice_i_redni_brojevi_nisu_greska():
    m = compute_metrics("<p>Radimo to itd. i dalje, a 12. oktobra je praznik.</p>")
    assert m["tipografija_greske"] == 0


def test_tipografija_nesparen_navodnik():
    assert compute_metrics('<p>Rekao je "dobar dan.</p>')["tipografija_greske"] >= 1
    assert compute_metrics('<p>Rekao je "dobar dan".</p>')["tipografija_greske"] == 0
