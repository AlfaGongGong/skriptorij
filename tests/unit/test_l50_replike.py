# -*- coding: utf-8 -*-
"""L50: replika u navodnicima na početku odlomka -> crtica (core/tipografija.py)."""
import pytest

from core.tipografija import normaliziraj

PARA = [
    ("<p>„Neka dođu”, rekao sam.</p>", "<p>— Neka dođu — rekao sam.</p>"),
    ("<p>„Idemo!” rekao je.</p>", "<p>— Idemo! — rekao je.</p>"),
    ("<p>„Ne”, rekao je. „Idemo.”</p>", "<p>— Ne — rekao je. — Idemo.</p>"),
    ("<p>„A”, rekao je, „b.”</p>", "<p>— A — rekao je — b.</p>"),
    ("<p>„Dobro.” Okrenuo se.</p>", "<p>— Dobro. — Okrenuo se.</p>"),
    ("<p>„Dobro.”</p>", "<p>— Dobro.</p>"),
    ("<p>„A.” „B.”</p>", "<p>— A. — B.</p>"),
    ("<p>„Idemo kući,” reče.</p>", "<p>— Idemo kući, reče.</p>"),
    ("<p>„Ne znam.” — reče on.</p>", "<p>— Ne znam. — reče on.</p>"),
]
OSTAJE = [
    "<p>„Dobar dan” je bila šifra koju su koristili.</p>",
    "<p>On reče: „Ne znam.”</p>",
    "<p>„Reče”, „da” i „ne”.</p>",
    "<p>— Idemo — reče on.</p>",
]


@pytest.mark.parametrize("ulaz,izlaz", PARA)
def test_replika_u_crticu(ulaz, izlaz):
    assert normaliziraj(ulaz) == izlaz


@pytest.mark.parametrize("h", OSTAJE)
def test_nije_dijalog_ostaje(h):
    assert normaliziraj(h) == h


@pytest.mark.parametrize("ulaz,izlaz", PARA)
def test_idempotentno(ulaz, izlaz):
    assert normaliziraj(izlaz) == izlaz


def test_ascii_navodnici_na_pocetku():
    assert normaliziraj('<p>"Idemo kući," reče.</p>') == "<p>— Idemo kući, reče.</p>"


def test_unutar_inline_taga():
    assert normaliziraj("<p>„Idemo”, <em>reče</em> on.</p>") == "<p>— Idemo — <em>reče</em> on.</p>"
