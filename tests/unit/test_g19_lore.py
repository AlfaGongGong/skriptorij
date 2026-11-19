"""G19: lore enforcement (core/lore.py)."""
from core.lore import primijeni_kanon

T = {"Count": {"hr": "grof", "odbacene_varijante": ["knez", "Kont"]}, "Bajaz": {"hr": "Bajaz", "odbacene_varijante": ["Bayaz"]}}


def test_mala_i_velika_slova():
    t, n = primijeni_kanon("Knez je usao. Vidio je knez Bajaza.", T)
    assert t == "Grof je usao. Vidio je grof Bajaza." and n == 2


def test_verzali():
    t, n = primijeni_kanon("KNEZ I BAYAZ", T)
    assert t == "GROF I BAJAZ" and n == 2


def test_tagovi_i_atributi_netaknuti():
    t, n = primijeni_kanon('<p class="knez" id="Bayaz">knez</p>', T)
    assert t == '<p class="knez" id="Bayaz">grof</p>' and n == 1


def test_padezi_se_ne_diraju():
    t, n = primijeni_kanon("knezovi i kneza", T)
    assert t == "knezovi i kneza" and n == 0


def test_doslovna_zamjena():
    t, n = primijeni_kanon("Bayaz", {"B": {"hr": "Ba\\g<0>\\1", "odbacene_varijante": ["Bayaz"]}})
    assert t == "Ba\\g<0>\\1" and n == 1


def test_idempotentno_i_prazno():
    t, _ = primijeni_kanon("knez", T)
    t2, n2 = primijeni_kanon(t, T)
    assert t2 == t and n2 == 0
    assert primijeni_kanon("x", {}) == ("x", 0)
    assert primijeni_kanon("", T) == ("", 0)


def test_kriva_struktura_ne_pada():
    assert primijeni_kanon("knez", {"a": "nije dict", "b": {"hr": "", "odbacene_varijante": ["knez"]}}) == ("knez", 0)
