import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import verifier as V

G = '{"tip": "kriv_smisao", "en_fragment": "fair sideburns", "hr_fragment": "plavim bradavicama", "objasnjenje": "Znaci zalisci."}'
N = '{"tip": "kriv_smisao", "en_fragment": "a", "hr_fragment": "b", "objasnjenje": "Nema greške."}'


def test_visak_zagrade():
    o = V.izvuci_json('{"ok": false, "greske": [' + G + ']]}')
    assert o and len(o["greske"]) == 1


def test_odsjecen_odgovor_spasi_potpune():
    o = V.izvuci_json('{"ok": false, "greske": [' + G + ', ' + N + ', {"tip": "kriv_smisao')
    assert o and len(o["greske"]) == 2


def test_cista_proza_je_none():
    assert V.izvuci_json("Lord Jale napustio je dvor. je dobro. Provjerilo") is None


def test_normalan_json_nepromijenjen():
    o = V.izvuci_json('{"ok": true, "greske": []}')
    assert o == {"ok": True, "greske": []}


def test_samo_nema_greske_je_ok():
    raw = '{"ok": false, "greske": [' + N + ', ' + N.replace('"a"', '"c"') + ', {"tip": "kriv_smisao'
    r = V.obradi_odgovor(raw, "a c", "b d")
    assert r["status"] == "ok" and r["provjeren"]


def test_prava_greska_ostaje():
    raw = '{"ok": false, "greske": [' + G + ', {"tip": "kriv_smisao'
    r = V.obradi_odgovor(raw, "he had fair sideburns", "imao je plavim bradavicama")
    assert r["status"] == "greske" and len(r["greske"]) == 1
